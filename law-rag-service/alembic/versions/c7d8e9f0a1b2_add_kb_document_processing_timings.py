"""add kb document processing timings

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c7d8e9f0a1b2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "kb_document",
        sa.Column("upload_timings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="oa",
    )
    op.add_column(
        "kb_document",
        sa.Column("ingest_timings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="oa",
    )


def downgrade() -> None:
    op.drop_column("kb_document", "ingest_timings", schema="oa")
    op.drop_column("kb_document", "upload_timings", schema="oa")
