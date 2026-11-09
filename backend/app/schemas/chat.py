import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.languages import LANGUAGE_CODES

ResponseLanguage = Literal["match", "en", "hi", "bn", "mr", "pa", "fr"]


class _Scope(BaseModel):
    document_ids: list[uuid.UUID] | None = Field(
        default=None, max_length=100, description="Restrict retrieval to these documents (same workspace)."
    )
    languages: list[str] | None = Field(
        default=None, description="Restrict retrieval to chunks in these languages (rarely needed)."
    )

    @field_validator("languages")
    @classmethod
    def _supported(cls, value: list[str] | None) -> list[str] | None:
        if value:
            unknown = [v for v in value if v not in LANGUAGE_CODES]
            if unknown:
                raise ValueError(f"Unsupported language(s): {', '.join(unknown)}")
        return value or None


class SearchRequest(_Scope):
    workspace_id: uuid.UUID
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=50)
    rerank: bool = True


class QueryRequest(_Scope):
    workspace_id: uuid.UUID
    question: str = Field(min_length=1, max_length=2000)
    response_language: ResponseLanguage = "match"


class SummaryRequest(BaseModel):
    response_language: Literal["en", "hi", "bn", "mr", "pa", "fr"] = "en"


class RetrievedPassage(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    page_start: int
    page_end: int
    section_title: str | None
    language: str | None
    rank: int
    dense_rank: int | None
    dense_similarity: float | None
    bm25_rank: int | None
    bm25_score: float | None
    rrf_score: float
    rerank_score: float | None
    content: str | None = None


class RetrievalInfo(BaseModel):
    passages: list[RetrievedPassage]
    dense_candidates: int
    bm25_candidates: int
    fused_candidates: int
    reranked: bool
    reranker_model: str | None
    timings_ms: dict[str, float]


class SearchResponse(BaseModel):
    query_language: str | None
    query_language_status: str
    retrieval: RetrievalInfo
    notes: list[str]


class CitationOut(BaseModel):
    marker: int = Field(description="Number used in the answer text, e.g. [1].")
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    page_start: int
    page_end: int
    section_title: str | None
    source_language: str | None
    quoted_text: str = Field(description="Original-language source text (verbatim quote or stored passage).")
    quote_verified: bool = Field(description="True if the model's quote was found verbatim in the chunk.")
    quote_page: int | None = Field(
        default=None, description="Exact page of a verified quote, from stored page offsets (may be null)."
    )


class GenerationInfo(BaseModel):
    provider: str
    model: str
    duration_ms: float


class AnswerResponse(BaseModel):
    answer: str
    language: str
    query_language: str | None
    query_language_status: str
    evidence_sufficient: bool
    answer_source: Literal["model", "system"]
    citations: list[CitationOut]
    retrieval: RetrievalInfo | None
    generation: GenerationInfo | None
    warnings: list[str]
    disclaimer: str = "Information from your documents, not legal advice."


class ConversationCreate(BaseModel):
    workspace_id: uuid.UUID
    title: str | None = Field(default=None, max_length=200)


class MessageCreate(_Scope):
    content: str = Field(min_length=1, max_length=2000)
    response_language: ResponseLanguage = "match"


class NewConversationMessage(MessageCreate):
    workspace_id: uuid.UUID


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    language: str | None
    citations: list[dict[str, Any]] | None
    evidence_sufficient: bool | None
    details: dict[str, Any] | None
    created_at: datetime


class ConversationDetail(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageRead]


class MessageExchange(BaseModel):
    conversation_id: uuid.UUID
    user_message: MessageRead
    assistant_message: MessageRead
    answer: AnswerResponse
