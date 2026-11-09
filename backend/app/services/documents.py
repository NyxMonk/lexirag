import logging
import re
import unicodedata
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import InvalidUploadError, NotFoundError
from app.models import Document, ProcessingStatus, Workspace
from app.services.storage import LocalStorage

logger = logging.getLogger("lexirag.documents")

ALLOWED_EXTENSIONS = frozenset({".pdf"})
PDF_MIME_TYPES = frozenset({"application/pdf", "application/x-pdf"})
# Some clients cannot infer a type and send a generic one; content is still
# verified by magic bytes before it is accepted.
GENERIC_MIME_TYPES = frozenset({"application/octet-stream", ""})

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_filename(raw: str | None) -> str:
    """Return a display-safe base filename. Never used to build filesystem paths."""
    name = unicodedata.normalize("NFC", raw or "")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = _CONTROL_CHARS.sub("", name).strip().strip(".")
    if not name:
        name = "document.pdf"
    if len(name) > 255:
        stem, suffix = Path(name).stem, Path(name).suffix[:16]
        name = stem[: 255 - len(suffix)] + suffix
    return name


def validate_upload(filename: str, content_type: str | None) -> None:
    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise InvalidUploadError("Only PDF files (.pdf) are supported at the moment.")
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in PDF_MIME_TYPES | GENERIC_MIME_TYPES:
        raise InvalidUploadError(f"Unsupported content type '{mime}'. Upload a PDF document.")


def list_documents(
    db: Session,
    *,
    workspace_id: uuid.UUID | None,
    search: str | None,
    status: ProcessingStatus | None,
    limit: int,
    offset: int,
) -> list[Document]:
    stmt = select(Document)
    if workspace_id is not None:
        stmt = stmt.where(Document.workspace_id == workspace_id)
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Document.original_filename.ilike(f"%{escaped}%", escape="\\"))
    if status is not None:
        stmt = stmt.where(Document.processing_status == status.value)
    stmt = stmt.order_by(Document.created_at.desc(), Document.id).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())


def get_document(db: Session, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document not found.")
    return document


def create_document(
    db: Session,
    storage: LocalStorage,
    *,
    workspace_id: uuid.UUID,
    filename: str | None,
    content_type: str | None,
    source: BinaryIO,
    max_bytes: int,
) -> Document:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFoundError("Workspace not found.")

    original_filename = sanitize_filename(filename)
    validate_upload(original_filename, content_type)

    stored = storage.save_pdf(source, workspace_id, max_bytes)
    document = Document(
        workspace_id=workspace_id,
        original_filename=original_filename,
        stored_filename=stored.stored_filename,
        file_path=stored.relative_path,
        file_size=stored.size,
        mime_type="application/pdf",
        processing_status=ProcessingStatus.UPLOADED.value,
    )
    # Keep "recently active" workspace ordering meaningful.
    workspace.updated_at = func.now()
    try:
        db.add(document)
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(stored.relative_path)
        raise
    db.refresh(document)
    logger.info("Stored document %s (%d bytes) in workspace %s", document.id, stored.size, workspace_id)
    return document


def set_language_override(db: Session, document_id: uuid.UUID, language: str | None) -> Document:
    document = get_document(db, document_id)
    document.language_override = language
    db.commit()
    db.refresh(document)
    return document


def delete_document(db: Session, storage: LocalStorage, document_id: uuid.UUID) -> None:
    # Chunks and their embeddings are removed by ON DELETE CASCADE in the same transaction.
    document = get_document(db, document_id)
    path = document.file_path
    db.delete(document)
    db.commit()
    storage.delete(path)
    logger.info("Deleted document %s", document_id)
