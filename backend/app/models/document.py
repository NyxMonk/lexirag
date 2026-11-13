import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.chunk import DocumentChunk
    from app.models.workspace import Workspace


class ProcessingStatus(enum.StrEnum):
    UPLOADED = "uploaded"  # stored, not yet queued
    QUEUED = "queued"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETED = "completed"  # chunks and embeddings are stored and searchable
    FAILED = "failed"


IN_PROGRESS_STATUSES = frozenset(
    {
        ProcessingStatus.QUEUED,
        ProcessingStatus.EXTRACTING,
        ProcessingStatus.CHUNKING,
        ProcessingStatus.EMBEDDING,
        ProcessingStatus.INDEXING,
    }
)

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in ProcessingStatus)


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Relative to the configured storage directory; never an absolute path.
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # Language: detected by the pipeline; a user override takes precedence when set.
    detected_language: Mapped[str | None] = mapped_column(String(8))
    language_confidence: Mapped[float | None] = mapped_column(Float)
    language_override: Mapped[str | None] = mapped_column(String(8))
    # {"status": "detected|mixed|uncertain|unsupported", "distribution": {...}, "scripts": {...}}
    language_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    processing_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ProcessingStatus.UPLOADED.value
    )
    processing_error: Mapped[str | None] = mapped_column(Text)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    # Extraction facts and progress: OCR pages, empty pages, warnings, embedding progress.
    processing_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    workspace: Mapped["Workspace"] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def effective_language(self) -> str | None:
        return self.language_override or self.detected_language

    __table_args__ = (
        CheckConstraint(f"processing_status IN ({_STATUS_VALUES})", name="processing_status"),
        Index("ix_documents_workspace_id_created_at", "workspace_id", "created_at"),
        Index("ix_documents_processing_status", "processing_status"),
    )
