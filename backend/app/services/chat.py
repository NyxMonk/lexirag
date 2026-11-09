"""Question answering and conversation persistence on top of the RAG engine."""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import InvalidRequestError, NotFoundError
from app.models import Conversation, Document, Message, MessageRole, ProcessingStatus, Workspace
from app.rag.answering import Answer, AnswerEngine, new_conversation_title
from app.rag.embeddings import get_embedding_model
from app.rag.language import detect_language
from app.rag.llm import get_llm_provider, overridden_provider
from app.rag.reranking import get_reranker
from app.rag.retrieval import HybridRetriever, RetrievalResult, RetrievalScope
from app.schemas.chat import (
    AnswerResponse,
    CitationOut,
    ConversationDetail,
    GenerationInfo,
    MessageRead,
    RetrievalInfo,
    RetrievedPassage,
    SearchResponse,
)

logger = logging.getLogger("lexirag.chat")

HISTORY_TURNS = 4  # earlier messages passed to the model for follow-up questions


def build_scope(
    db: Session,
    workspace_id: uuid.UUID,
    document_ids: list[uuid.UUID] | None,
    languages: list[str] | None = None,
) -> RetrievalScope:
    """Validate that the workspace exists, every document belongs to it, and something is searchable."""
    if db.get(Workspace, workspace_id) is None:
        raise NotFoundError("Workspace not found.")
    if document_ids:
        unique = list(dict.fromkeys(document_ids))
        rows = db.execute(
            select(Document.id, Document.processing_status).where(
                Document.id.in_(unique), Document.workspace_id == workspace_id
            )
        ).all()
        found = {r.id: r.processing_status for r in rows}
        # Documents from other workspaces are reported as not found (no cross-workspace probing).
        missing = [str(d) for d in unique if d not in found]
        if missing:
            raise NotFoundError("One or more documents were not found in this workspace.", details={"missing": missing})
        not_ready = [str(d) for d, s in found.items() if s != ProcessingStatus.COMPLETED.value]
        if len(not_ready) == len(found):
            raise InvalidRequestError(
                "The selected documents have not finished processing yet.", details={"not_ready": not_ready}
            )
        document_ids = unique
    else:
        ready = db.scalar(
            select(func.count(Document.id)).where(
                Document.workspace_id == workspace_id,
                Document.processing_status == ProcessingStatus.COMPLETED.value,
            )
        )
        if not ready:
            raise InvalidRequestError("This workspace has no processed documents to search yet.")
    return RetrievalScope(workspace_id=workspace_id, document_ids=document_ids, languages=languages)


def _retriever() -> HybridRetriever:
    return HybridRetriever(get_settings(), get_embedding_model(), get_reranker())


def _engine() -> AnswerEngine:
    # Fail fast on missing LLM configuration, before loading models or retrieving.
    llm = overridden_provider() or get_llm_provider()
    return AnswerEngine(get_settings(), _retriever(), llm)


def _retrieval_info(result: RetrievalResult, include_content: bool) -> RetrievalInfo:
    return RetrievalInfo(
        passages=[
            RetrievedPassage(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                document_name=c.document_name,
                page_start=c.page_start,
                page_end=c.page_end,
                section_title=c.section_title,
                language=c.language,
                rank=c.rank,
                dense_rank=c.dense_rank,
                dense_similarity=round(c.dense_similarity, 4) if c.dense_similarity is not None else None,
                bm25_rank=c.bm25_rank,
                bm25_score=round(c.bm25_score, 4) if c.bm25_score is not None else None,
                rrf_score=round(c.rrf_score, 5),
                rerank_score=round(c.rerank_score, 4) if c.rerank_score is not None else None,
                content=c.content if include_content else None,
            )
            for c in result.chunks
        ],
        dense_candidates=result.dense_candidates,
        bm25_candidates=result.bm25_candidates,
        fused_candidates=result.fused_candidates,
        reranked=result.reranked,
        reranker_model=result.reranker_model,
        timings_ms=result.timings_ms,
    )


def to_response(answer: Answer) -> AnswerResponse:
    return AnswerResponse(
        answer=answer.answer,
        language=answer.language,
        query_language=answer.query_language,
        query_language_status=answer.query_language_status,
        evidence_sufficient=answer.evidence_sufficient,
        answer_source=answer.answer_source,  # type: ignore[arg-type]
        citations=[
            CitationOut(
                marker=c.marker,
                chunk_id=c.chunk.chunk_id,
                document_id=c.chunk.document_id,
                document_name=c.chunk.document_name,
                page_start=c.chunk.page_start,
                page_end=c.chunk.page_end,
                # The section containing a verified quote; otherwise the chunk's first section.
                section_title=c.quote_section or c.chunk.section_title,
                source_language=c.chunk.language,
                quoted_text=c.quoted_text,
                quote_verified=c.quote_verified,
                quote_page=c.quote_page,
            )
            for c in answer.citations
        ],
        retrieval=_retrieval_info(answer.retrieval, include_content=False) if answer.retrieval else None,
        generation=GenerationInfo(
            provider=answer.generation.provider,
            model=answer.generation.model,
            duration_ms=round(answer.generation.duration_ms, 1),
        )
        if answer.generation
        else None,
        warnings=answer.warnings,
    )


def search(
    db: Session,
    workspace_id: uuid.UUID,
    query: str,
    document_ids: list[uuid.UUID] | None,
    languages: list[str] | None,
    top_k: int,
    rerank: bool,
) -> SearchResponse:
    scope = build_scope(db, workspace_id, document_ids, languages)
    detected = detect_language(query)
    result = _retriever().retrieve(db, query, scope, top_k=top_k, rerank=rerank)
    return SearchResponse(
        query_language=detected.language,
        query_language_status=detected.status,
        retrieval=_retrieval_info(result, include_content=True),
        notes=result.notes,
    )


def query(
    db: Session,
    workspace_id: uuid.UUID,
    question: str,
    document_ids: list[uuid.UUID] | None,
    languages: list[str] | None,
    response_language: str,
) -> AnswerResponse:
    scope = build_scope(db, workspace_id, document_ids, languages)
    engine = _engine()
    answer = engine.answer(db, question, scope, response_language=response_language)
    logger.info(
        "Answered query in workspace %s: lang=%s->%s citations=%d sufficient=%s",
        workspace_id, answer.query_language, answer.language, len(answer.citations), answer.evidence_sufficient,
    )
    return to_response(answer)


# ── conversations ──
def create_conversation(db: Session, workspace_id: uuid.UUID, title: str | None) -> Conversation:
    if db.get(Workspace, workspace_id) is None:
        raise NotFoundError("Workspace not found.")
    conversation = Conversation(workspace_id=workspace_id, title=(title or "New conversation").strip()[:200])
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_conversation(db: Session, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found.")
    return conversation


def conversation_detail(db: Session, conversation_id: uuid.UUID) -> ConversationDetail:
    conversation = get_conversation(db, conversation_id)
    return ConversationDetail(
        id=conversation.id,
        workspace_id=conversation.workspace_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessageRead.model_validate(m) for m in conversation.messages],
    )


def delete_conversation(db: Session, conversation_id: uuid.UUID) -> None:
    db.delete(get_conversation(db, conversation_id))
    db.commit()


def send_message(
    db: Session,
    conversation_id: uuid.UUID | None,
    content: str,
    document_ids: list[uuid.UUID] | None,
    languages: list[str] | None,
    response_language: str,
    workspace_id: uuid.UUID | None = None,
) -> tuple[Message, Message, AnswerResponse]:
    """Answer and persist one exchange.

    With ``conversation_id=None`` a new conversation is created only after the answer
    succeeds, in the same transaction as its messages, so failures never leave empty
    conversations behind.
    """
    if conversation_id is not None:
        existing = get_conversation(db, conversation_id)
        workspace_id = existing.workspace_id
        previous = existing.messages[-HISTORY_TURNS:]
    elif workspace_id is None:
        raise InvalidRequestError("workspace_id is required to start a conversation.")
    else:
        previous = []
    scope = build_scope(db, workspace_id, document_ids, languages)
    engine = _engine()

    history = [(m.role, m.content) for m in previous if m.role in (MessageRole.USER, MessageRole.ASSISTANT)]
    answer = engine.answer(db, content, scope, response_language=response_language, history=history)
    response = to_response(answer)
    # The retrieval stage issued SET LOCAL statements; start a clean transaction for the writes.
    db.rollback()

    if conversation_id is None:
        conversation = Conversation(workspace_id=workspace_id, title=new_conversation_title(content))
        db.add(conversation)
        db.flush()
    else:
        conversation = get_conversation(db, conversation_id)
    user_message = Message(
        conversation_id=conversation.id,
        role=MessageRole.USER.value,
        content=content,
        language=answer.query_language,
        details={"document_ids": [str(d) for d in document_ids] if document_ids else None,
                 "response_language": response_language},
    )
    assistant_message = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT.value,
        content=response.answer,
        language=response.language,
        citations=[c.model_dump(mode="json") for c in response.citations],
        evidence_sufficient=response.evidence_sufficient,
        details={
            "answer_source": response.answer_source,
            "query_language": response.query_language,
            "warnings": response.warnings,
            "generation": response.generation.model_dump() if response.generation else None,
            "retrieval": response.retrieval.model_dump(mode="json") if response.retrieval else None,
        },
    )
    db.add(user_message)
    db.flush()  # keeps created_at ordering: user message first
    db.add(assistant_message)
    if not conversation.messages or conversation.title == "New conversation":
        conversation.title = new_conversation_title(content)
    conversation.updated_at = func.now()
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    return user_message, assistant_message, response


def summarize_document(db: Session, document_id: uuid.UUID, response_language: str) -> AnswerResponse:
    """Summarise one processed document from its stored chunks, with page citations."""
    from app.models import DocumentChunk
    from app.rag.retrieval import RetrievedChunk

    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document not found.")
    if document.processing_status != ProcessingStatus.COMPLETED.value:
        raise InvalidRequestError("This document has not finished processing yet.")
    llm = overridden_provider() or get_llm_provider()
    rows = db.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index)
    ).all()
    chunks = [
        RetrievedChunk(
            chunk_id=c.id, document_id=c.document_id, document_name=document.original_filename, content=c.content,
            page_start=c.page_start, page_end=c.page_end, section_title=c.section_title, language=c.language,
            chunk_index=c.chunk_index, page_spans=c.page_spans, section_spans=c.section_spans,
        )
        for c in rows
    ]
    engine = AnswerEngine(get_settings(), None, llm)  # type: ignore[arg-type]  # no retrieval needed
    answer = engine.summarize(document.original_filename, chunks, response_language=response_language)
    logger.info("Summarised document %s (%d chunks, lang=%s)", document_id, len(chunks), answer.language)
    return to_response(answer)
