import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.languages import LANGUAGE_CODES
from app.models.document import ProcessingStatus


class ProcessingProgress(BaseModel):
    done: int
    total: int


class DocumentRead(BaseModel):
    """Public document metadata. Storage paths are intentionally not exposed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    original_filename: str
    file_size: int
    mime_type: str
    detected_language: str | None
    language_confidence: float | None = None
    language_override: str | None = None
    effective_language: str | None = None
    language_status: str | None = None
    processing_status: ProcessingStatus
    processing_error: str | None = None
    processing_progress: ProcessingProgress | None = None
    page_count: int | None = None
    chunk_count: int | None = None
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, document: Any) -> "DocumentRead":
        read = cls.model_validate(document)
        details = document.processing_details or {}
        embedding = details.get("embedding") if isinstance(details, dict) else None
        progress = None
        if isinstance(embedding, dict) and "done" in embedding and "total" in embedding:
            progress = ProcessingProgress(done=embedding["done"], total=embedding["total"])
        language_status = (document.language_details or {}).get("status") if document.language_details else None
        return read.model_copy(update={"processing_progress": progress, "language_status": language_status})


class DocumentStatus(BaseModel):
    id: uuid.UUID
    processing_status: ProcessingStatus
    processing_error: str | None
    processing_progress: ProcessingProgress | None
    page_count: int | None
    chunk_count: int | None
    detected_language: str | None
    language_status: str | None
    processing_started_at: datetime | None
    processing_completed_at: datetime | None
    extraction: dict[str, Any] | None = Field(
        default=None, description="Pages read as text, OCR'd pages, empty pages and warnings."
    )


class DocumentUpdate(BaseModel):
    """Set or clear (null) the user's language override."""

    language_override: str | None

    @field_validator("language_override")
    @classmethod
    def _supported(cls, value: str | None) -> str | None:
        if value is not None and value not in LANGUAGE_CODES:
            raise ValueError(f"Unsupported language '{value}'. Use one of: {', '.join(sorted(LANGUAGE_CODES))}")
        return value


class ProcessRequest(BaseModel):
    force: bool = Field(default=False, description="Re-index a document that is already completed.")


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    page_start: int
    page_end: int
    language: str | None
    section_title: str | None
    token_count: int
    created_at: datetime


class ChunkPage(BaseModel):
    items: list[ChunkRead]
    total: int
