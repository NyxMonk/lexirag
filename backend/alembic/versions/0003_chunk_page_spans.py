"""Per-page and per-section offsets inside each chunk, for exact citations.

A chunk can cross a page break or merge several short sections. These columns
record character offsets into ``content`` so a verified quotation can be mapped
to the precise page and section it appears in:

* ``page_spans``: [[page, start, end], ...]
* ``section_spans``: [[start, "section title"], ...] (a section runs until the next start)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("page_spans", postgresql.JSONB(), nullable=True))
    op.add_column("document_chunks", sa.Column("section_spans", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_chunks", "section_spans")
    op.drop_column("document_chunks", "page_spans")
