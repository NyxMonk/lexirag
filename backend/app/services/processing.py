"""Document ingestion pipeline and its in-process job queue.

uploaded/failed/completed --claim--> queued -> extracting -> chunking -> embedding -> indexing -> completed
                                                    \\______________ any error ______________/-> failed

* Claims are atomic (``UPDATE ... WHERE status IN (...)``), so two requests can
  never process the same document concurrently.
* One worker thread processes documents sequentially, which bounds memory use
  on laptops; upload requests return immediately.
* Indexing replaces a document's chunks inside one transaction, so re-processing
  is idempotent and searches never see a half-indexed document.
* Documents left mid-pipeline by a restart are re-queued at startup.
"""

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.database.session import SessionLocal
from app.models import IN_PROGRESS_STATUSES, Document, DocumentChunk, ProcessingStatus
from app.rag.chunking import LegalChunker
from app.rag.embeddings import get_embedding_model
from app.rag.errors import ExtractionError, RagError
from app.rag.extraction import extract_pdf
from app.rag.language import detect_document_language
from app.services.storage import LocalStorage

logger = logging.getLogger("lexirag.processing")

CLAIMABLE = {ProcessingStatus.UPLOADED, ProcessingStatus.FAILED}
CLAIMABLE_FORCED = CLAIMABLE | {ProcessingStatus.COMPLETED}


class _ProcessingQueue:
    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()
        self._scheduled: set[uuid.UUID] = set()

    def submit(self, document_id: uuid.UUID) -> None:
        with self._lock:
            if document_id in self._scheduled:
                return
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lexirag-processing")
            self._scheduled.add(document_id)
            self._executor.submit(self._run, document_id)

    def _run(self, document_id: uuid.UUID) -> None:
        try:
            run_pipeline(document_id)
        finally:
            with self._lock:
                self._scheduled.discard(document_id)

    def pending(self) -> int:
        with self._lock:
            return len(self._scheduled)

    def shutdown(self, wait: bool = False) -> None:
        with self._lock:
            executor, self._executor = self._executor, None
        if executor:
            executor.shutdown(wait=wait, cancel_futures=True)


queue = _ProcessingQueue()


# ── claiming ──
def claim_for_processing(db: Session, document_id: uuid.UUID, *, force: bool = False, retry_only: bool = False) -> None:
    allowed = {ProcessingStatus.FAILED} if retry_only else (CLAIMABLE_FORCED if force else CLAIMABLE)
    claimed = db.execute(
        update(Document)
        .where(Document.id == document_id, Document.processing_status.in_([s.value for s in allowed]))
        .values(
            processing_status=ProcessingStatus.QUEUED.value,
            processing_error=None,
            processing_details=None,
            processing_started_at=None,
            processing_completed_at=None,
            updated_at=func.now(),
        )
        .returning(Document.id)
    ).scalar_one_or_none()
    db.commit()
    if claimed is not None:
        return
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document not found.")
    status = document.processing_status
    if status in IN_PROGRESS_STATUSES:
        raise ConflictError("This document is already being processed.", details={"status": status})
    if retry_only:
        raise ConflictError("Only documents whose processing failed can be retried.", details={"status": status})
    raise ConflictError(
        "This document is already processed. Pass force=true to re-index it.", details={"status": status}
    )


def enqueue(db: Session, document_id: uuid.UUID, *, force: bool = False, retry_only: bool = False) -> None:
    claim_for_processing(db, document_id, force=force, retry_only=retry_only)
    queue.submit(document_id)


def recover_interrupted() -> int:
    """Re-queue documents that were mid-pipeline when the process stopped."""
    with SessionLocal() as db:
        ids = db.execute(
            update(Document)
            .where(Document.processing_status.in_([s.value for s in IN_PROGRESS_STATUSES]))
            .values(processing_status=ProcessingStatus.QUEUED.value, updated_at=func.now())
            .returning(Document.id)
        ).scalars().all()
        db.commit()
    for document_id in ids:
        queue.submit(document_id)
    if ids:
        logger.info("Re-queued %d interrupted document(s)", len(ids))
    return len(ids)


# ── pipeline ──
def _set_status(document_id: uuid.UUID, status: ProcessingStatus, **values: Any) -> bool:
    """Update status in its own short transaction. Returns False if the document is gone."""
    with SessionLocal() as db:
        result = db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(processing_status=status.value, updated_at=func.now(), **values)
        )
        db.commit()
        return result.rowcount > 0


def _merge_details(document_id: uuid.UUID, patch: dict[str, Any]) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None:
            return
        document.processing_details = {**(document.processing_details or {}), **patch}
        db.commit()


def run_pipeline(document_id: uuid.UUID) -> None:
    settings = get_settings()
    started = time.perf_counter()
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None or document.processing_status != ProcessingStatus.QUEUED.value:
            logger.info("Skipping document %s (missing or not queued)", document_id)
            return
        workspace_id = document.workspace_id
        relative_path = document.file_path

    try:
        if not _set_status(document_id, ProcessingStatus.EXTRACTING, processing_started_at=datetime.now(UTC)):
            return
        storage = LocalStorage(settings.storage_path)
        path = storage.resolve(relative_path)
        if not path.is_file():
            raise ExtractionError("The stored PDF file is missing.")
        extraction = extract_pdf(
            path,
            ocr_enabled=settings.ocr_enabled,
            tesseract_cmd=settings.tesseract_cmd,
            ocr_languages=settings.ocr_languages,
            ocr_dpi=settings.ocr_dpi,
            ocr_min_text_chars=settings.ocr_min_text_chars,
            max_pages=settings.max_pages,
        )
        summary = extraction.summary()
        if extraction.total_chars == 0:
            reason = " ".join(extraction.warnings) or "The PDF contains no extractable text."
            raise ExtractionError(f"No text could be extracted. {reason}".strip())

        language = detect_document_language([p.text for p in extraction.pages])
        if not _set_status(
            document_id,
            ProcessingStatus.CHUNKING,
            page_count=extraction.page_count,
            detected_language=language.language,
            language_confidence=round(language.confidence, 3) if language.language else None,
            language_details=language.as_details(),
            processing_details={"extraction": summary},
        ):
            return

        embedder = get_embedding_model()
        chunker = LegalChunker(
            embedder.token_counter(),
            target_tokens=settings.chunk_target_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
            min_tokens=settings.chunk_min_tokens,
        )
        with SessionLocal() as db:
            doc = db.get(Document, document_id)
            default_language = doc.effective_language if doc else language.language
        chunks = chunker.chunk(extraction.pages, default_language=default_language)
        if not chunks:
            raise ExtractionError("The extracted text produced no chunks.")

        if not _set_status(document_id, ProcessingStatus.EMBEDDING):
            return
        last_report = [0.0]

        def progress(done: int, total: int) -> None:
            now = time.perf_counter()
            if done == total or now - last_report[0] > 1.0:
                last_report[0] = now
                _merge_details(document_id, {"embedding": {"done": done, "total": total}})

        vectors = embedder.embed_documents([c.content for c in chunks], progress=progress)

        if not _set_status(document_id, ProcessingStatus.INDEXING):
            return
        with SessionLocal() as db:
            db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
            db.add_all(
                DocumentChunk(
                    document_id=document_id,
                    workspace_id=workspace_id,
                    chunk_index=c.index,
                    content=c.content,
                    embedding=vectors[i].tolist(),
                    page_start=c.page_start,
                    page_end=c.page_end,
                    language=c.language,
                    section_title=c.section_title,
                    token_count=c.token_count,
                    page_spans=[list(span) for span in c.page_spans],
                    section_spans=[list(span) for span in c.section_spans],
                )
                for i, c in enumerate(chunks)
            )
            document = db.get(Document, document_id)
            if document is None:
                db.rollback()
                return
            document.processing_status = ProcessingStatus.COMPLETED.value
            document.chunk_count = len(chunks)
            document.processing_completed_at = datetime.now(UTC)
            document.processing_error = None
            document.processing_details = {
                **(document.processing_details or {}),
                "chunking": {
                    "chunks": len(chunks),
                    "target_tokens": settings.chunk_target_tokens,
                    "overlap_tokens": settings.chunk_overlap_tokens,
                    "token_counter": getattr(chunker.counter, "name", "unknown"),
                },
                "embedding": {"done": len(chunks), "total": len(chunks), "model": embedder.model_id,
                              "device": embedder.device},
                "duration_seconds": round(time.perf_counter() - started, 1),
            }
            db.commit()
        logger.info("Indexed document %s: %d chunks in %.1fs", document_id, len(chunks), time.perf_counter() - started)
    except IntegrityError:
        # The document (or its workspace) was deleted while it was being processed.
        logger.info("Document %s was deleted during processing", document_id)
    except RagError as exc:
        logger.warning("Processing failed for %s: %s", document_id, exc.message)
        _set_status(document_id, ProcessingStatus.FAILED, processing_error=exc.message[:2000])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected processing failure for %s", document_id)
        _set_status(
            document_id,
            ProcessingStatus.FAILED,
            processing_error=f"Unexpected processing error ({exc.__class__.__name__}). See the backend log.",
        )


def queue_depth() -> int:
    return queue.pending()


def chunk_stats(db: Session, document_id: uuid.UUID) -> int:
    return db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id)) or 0
