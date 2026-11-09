"""Hybrid retrieval: pgvector dense search + BM25, fused with RRF, then reranked.

Every query is scoped to exactly one workspace; document and language filters
narrow it further. Isolation is enforced in SQL (``workspace_id = :ws``) for
dense search and by building BM25 indexes per workspace.
"""

import logging
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Document, DocumentChunk
from app.rag.bm25 import BM25Index
from app.rag.embeddings import EmbeddingModel
from app.rag.errors import RagError
from app.rag.fusion import reciprocal_rank_fusion
from app.rag.reranking import Reranker

logger = logging.getLogger("lexirag.retrieval")


@dataclass
class RetrievalScope:
    workspace_id: uuid.UUID
    document_ids: list[uuid.UUID] | None = None
    languages: list[str] | None = None


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    content: str
    page_start: int
    page_end: int
    section_title: str | None
    language: str | None
    chunk_index: int
    page_spans: list[list[int]] | None = None
    section_spans: list[list] | None = None
    rank: int = 0
    dense_rank: int | None = None
    dense_similarity: float | None = None
    bm25_rank: int | None = None
    bm25_score: float | None = None
    rrf_score: float = 0.0
    rerank_score: float | None = None


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    dense_candidates: int
    bm25_candidates: int
    fused_candidates: int
    reranked: bool
    reranker_model: str | None
    timings_ms: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class _WorkspaceBM25Cache:
    """Per-workspace BM25 indexes, rebuilt when the workspace's chunks change."""

    def __init__(self, max_workspaces: int = 8) -> None:
        self._items: OrderedDict[uuid.UUID, tuple[tuple, BM25Index, dict[uuid.UUID, uuid.UUID]]] = OrderedDict()
        self._lock = threading.Lock()
        self._max = max_workspaces

    def get(self, db: Session, workspace_id: uuid.UUID) -> tuple[BM25Index, dict[uuid.UUID, uuid.UUID]]:
        version = tuple(
            db.execute(
                select(func.count(DocumentChunk.id), func.max(DocumentChunk.created_at)).where(
                    DocumentChunk.workspace_id == workspace_id
                )
            ).one()
        )
        with self._lock:
            cached = self._items.get(workspace_id)
            if cached and cached[0] == version:
                self._items.move_to_end(workspace_id)
                return cached[1], cached[2]
        rows = db.execute(
            select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.content).where(
                DocumentChunk.workspace_id == workspace_id
            )
        ).all()
        index = BM25Index([r.id for r in rows], [r.content for r in rows])
        doc_of = {r.id: r.document_id for r in rows}
        with self._lock:
            self._items[workspace_id] = (version, index, doc_of)
            self._items.move_to_end(workspace_id)
            while len(self._items) > self._max:
                self._items.popitem(last=False)
        return index, doc_of


_bm25_cache = _WorkspaceBM25Cache()


class HybridRetriever:
    def __init__(self, settings: Settings, embedder: EmbeddingModel, reranker: Reranker | None) -> None:
        self.settings = settings
        self.embedder = embedder
        self.reranker = reranker

    # ── stages ──
    def dense_search(
        self, db: Session, query_vector: list[float], scope: RetrievalScope, top_k: int
    ) -> list[tuple[uuid.UUID, float]]:
        distance = DocumentChunk.embedding.cosine_distance(query_vector)
        stmt = select(DocumentChunk.id, distance.label("distance")).where(
            DocumentChunk.workspace_id == scope.workspace_id
        )
        if scope.document_ids:
            stmt = stmt.where(DocumentChunk.document_id.in_(scope.document_ids))
        if scope.languages:
            stmt = stmt.where(DocumentChunk.language.in_(scope.languages))
        stmt = stmt.order_by(distance).limit(top_k)
        # Filtered HNSW scans can return too few rows; iterative scans (pgvector 0.8) keep going.
        db.execute(text("SET LOCAL hnsw.ef_search = 100"))
        db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        rows = db.execute(stmt).all()
        # relaxed_order may return slightly out-of-order rows; re-sort by exact distance.
        return sorted(((r.id, 1.0 - float(r.distance)) for r in rows), key=lambda x: -x[1])

    def bm25_search(self, db: Session, query: str, scope: RetrievalScope, top_k: int) -> list[tuple[uuid.UUID, float]]:
        index, doc_of = _bm25_cache.get(db, scope.workspace_id)
        allowed: set[object] | None = None
        if scope.document_ids:
            wanted = set(scope.document_ids)
            allowed = {cid for cid, did in doc_of.items() if did in wanted}
        if scope.languages:
            lang_rows = db.execute(
                select(DocumentChunk.id).where(
                    DocumentChunk.workspace_id == scope.workspace_id,
                    DocumentChunk.language.in_(scope.languages),
                )
            ).scalars()
            lang_ids = set(lang_rows)
            allowed = lang_ids if allowed is None else allowed & lang_ids
        return [(k, s) for k, s in index.search(query, top_k, allowed=allowed)]  # type: ignore[misc]

    # ── pipeline ──
    def retrieve(
        self,
        db: Session,
        query: str,
        scope: RetrievalScope,
        *,
        top_k: int | None = None,
        rerank: bool = True,
    ) -> RetrievalResult:
        s = self.settings
        final_k = top_k or s.retrieval_final_top_k
        timings: dict[str, float] = {}
        notes: list[str] = []

        started = time.perf_counter()
        query_vector = self.embedder.embed_query(query).tolist()
        timings["embed_query"] = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        dense = self.dense_search(db, query_vector, scope, s.retrieval_dense_top_k)
        timings["dense"] = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        sparse = self.bm25_search(db, query, scope, s.retrieval_bm25_top_k)
        timings["bm25"] = (time.perf_counter() - started) * 1000

        fused = reciprocal_rank_fusion([[cid for cid, _ in dense], [cid for cid, _ in sparse]], k=s.retrieval_rrf_k)
        dense_info = {cid: (rank, sim) for rank, (cid, sim) in enumerate(dense, start=1)}
        bm25_info = {cid: (rank, score) for rank, (cid, score) in enumerate(sparse, start=1)}

        candidate_ids = [cid for cid, _ in fused[: max(s.rerank_candidates, final_k)]]
        chunks = self._load_chunks(db, candidate_ids, scope.workspace_id)
        rrf = dict(fused)
        for chunk in chunks:
            if chunk.chunk_id in dense_info:
                chunk.dense_rank, chunk.dense_similarity = dense_info[chunk.chunk_id]
            if chunk.chunk_id in bm25_info:
                chunk.bm25_rank, chunk.bm25_score = bm25_info[chunk.chunk_id]
            chunk.rrf_score = rrf[chunk.chunk_id]
        chunks.sort(key=lambda c: -c.rrf_score)

        reranked = False
        if rerank and self.reranker is not None and chunks:
            started = time.perf_counter()
            try:
                scores = self.reranker.score(query, [c.content for c in chunks])
                for chunk, score in zip(chunks, scores, strict=True):
                    chunk.rerank_score = score
                chunks.sort(key=lambda c: -(c.rerank_score or 0.0))
                reranked = True
            except RagError as exc:
                notes.append(f"Reranking skipped: {exc.message}")
                logger.warning("Reranking skipped: %s", exc.message)
            timings["rerank"] = (time.perf_counter() - started) * 1000
        elif rerank and self.reranker is None:
            notes.append("Reranking is disabled (RERANKER_ENABLED=false); fused order is used.")

        final = chunks[:final_k]
        for rank, chunk in enumerate(final, start=1):
            chunk.rank = rank
        return RetrievalResult(
            chunks=final,
            dense_candidates=len(dense),
            bm25_candidates=len(sparse),
            fused_candidates=len(fused),
            reranked=reranked,
            reranker_model=getattr(self.reranker, "model_id", None) if reranked else None,
            timings_ms={k: round(v, 1) for k, v in timings.items()},
            notes=notes,
        )

    @staticmethod
    def _load_chunks(db: Session, ids: list[uuid.UUID], workspace_id: uuid.UUID) -> list[RetrievedChunk]:
        if not ids:
            return []
        rows = db.execute(
            select(DocumentChunk, Document.original_filename)
            .join(Document, Document.id == DocumentChunk.document_id)
            # Defence in depth: re-check the workspace on the final rows.
            .where(DocumentChunk.id.in_(ids), DocumentChunk.workspace_id == workspace_id)
        ).all()
        return [
            RetrievedChunk(
                chunk_id=c.id,
                document_id=c.document_id,
                document_name=name,
                content=c.content,
                page_start=c.page_start,
                page_end=c.page_end,
                section_title=c.section_title,
                language=c.language,
                chunk_index=c.chunk_index,
                page_spans=c.page_spans,
                section_spans=c.section_spans,
            )
            for c, name in rows
        ]
