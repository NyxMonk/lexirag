"""RAG engine: document chunks with embeddings, processing pipeline state, answer metadata.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# BAAI/bge-m3 dense dimension. Changing the embedding model to one with a different
# dimension requires a new migration (and re-processing every document).
EMBEDDING_DIMENSION = 1024

NEW_STATUSES = "'uploaded', 'queued', 'extracting', 'chunking', 'embedding', 'indexing', 'completed', 'failed'"
OLD_STATUSES = "'uploaded', 'processing', 'ready', 'failed'"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── documents: pipeline status vocabulary and metadata ──
    op.drop_constraint(op.f("ck_documents_processing_status"), "documents", type_="check")
    op.execute("UPDATE documents SET processing_status = 'queued' WHERE processing_status = 'processing'")
    op.execute("UPDATE documents SET processing_status = 'completed' WHERE processing_status = 'ready'")
    op.create_check_constraint(
        op.f("ck_documents_processing_status"), "documents", f"processing_status IN ({NEW_STATUSES})"
    )
    op.add_column("documents", sa.Column("language_confidence", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("language_override", sa.String(length=8), nullable=True))
    op.add_column("documents", sa.Column("language_details", postgresql.JSONB(), nullable=True))
    op.add_column("documents", sa.Column("processing_error", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("page_count", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("chunk_count", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("processing_details", postgresql.JSONB(), nullable=True))

    # ── document_chunks ──
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("section_title", sa.String(length=300), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_document_chunks_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_id_chunk_index"),
        sa.CheckConstraint("page_start >= 1 AND page_end >= page_start", name=op.f("ck_document_chunks_page_range")),
    )
    op.create_index("ix_document_chunks_workspace_id", "document_chunks", ["workspace_id"])
    op.create_index("ix_document_chunks_language", "document_chunks", ["language"])
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # ── messages: grounded answer metadata ──
    op.add_column("messages", sa.Column("language", sa.String(length=8), nullable=True))
    op.add_column("messages", sa.Column("citations", postgresql.JSONB(), nullable=True))
    op.add_column("messages", sa.Column("evidence_sufficient", sa.Boolean(), nullable=True))
    op.add_column("messages", sa.Column("details", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "details")
    op.drop_column("messages", "evidence_sufficient")
    op.drop_column("messages", "citations")
    op.drop_column("messages", "language")

    op.drop_table("document_chunks")

    for column in (
        "processing_details",
        "chunk_count",
        "page_count",
        "processing_completed_at",
        "processing_started_at",
        "processing_error",
        "language_details",
        "language_override",
        "language_confidence",
    ):
        op.drop_column("documents", column)
    op.drop_constraint(op.f("ck_documents_processing_status"), "documents", type_="check")
    op.execute(
        "UPDATE documents SET processing_status = 'processing' "
        "WHERE processing_status IN ('queued', 'extracting', 'chunking', 'embedding', 'indexing')"
    )
    op.execute("UPDATE documents SET processing_status = 'ready' WHERE processing_status = 'completed'")
    op.create_check_constraint(
        op.f("ck_documents_processing_status"), "documents", f"processing_status IN ({OLD_STATUSES})"
    )
