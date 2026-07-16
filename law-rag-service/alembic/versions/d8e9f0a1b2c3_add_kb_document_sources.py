"""add kb document sources

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_document_source",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("attachment_id", sa.BigInteger(), nullable=False),
        sa.Column("source_title", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ingest_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("image_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("image_kept", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("image_filtered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("body_markdown", sa.Text(), nullable=True),
        sa.Column("description_summary", sa.Text(), nullable=True),
        sa.Column("upload_timings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ingest_timings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["oa.kb_document.id"], name="fk_kb_document_source_document"
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"], ["oa.sys_attachment.id"], name="fk_kb_document_source_attachment"
        ),
        schema="oa",
    )
    op.create_index(
        "ix_kb_document_source_document_order",
        "kb_document_source",
        ["document_id", "sort_order", "id"],
        schema="oa",
    )
    op.create_index(
        "uk_kb_document_source_active_attachment",
        "kb_document_source",
        ["attachment_id"],
        unique=True,
        schema="oa",
        postgresql_where=sa.text("deleted_at IS NULL AND status = 'active'"),
    )
    op.create_index(
        "uk_kb_document_source_primary",
        "kb_document_source",
        ["document_id"],
        unique=True,
        schema="oa",
        postgresql_where=sa.text(
            "is_primary IS TRUE AND deleted_at IS NULL AND status = 'active'"
        ),
    )
    op.execute(
        """
        INSERT INTO oa.kb_document_source (
            document_id, attachment_id, source_title, sort_order, is_primary,
            ingest_status, chunk_count, image_total, image_kept, image_filtered,
            body_markdown, description_summary, upload_timings, ingest_timings,
            created_at, updated_at, status
        )
        SELECT
            d.id, d.attachment_id,
            COALESCE(NULLIF(a.original_file_name, ''), NULLIF(a.file_name, ''), d.doc_title),
            0, TRUE, d.embedding_status, 0,
            COALESCE(d.image_total, 0), COALESCE(d.image_kept, 0),
            COALESCE(d.image_filtered, 0), d.body_markdown,
            d.description_summary, d.upload_timings, d.ingest_timings,
            d.created_at, COALESCE(d.updated_at, d.created_at), 'active'
        FROM oa.kb_document d
        JOIN oa.sys_attachment a ON a.id = d.attachment_id
        WHERE d.attachment_id IS NOT NULL
          AND d.deleted_at IS NULL
          AND d.status = 'active'
          AND NOT EXISTS (
              SELECT 1 FROM oa.kb_document_source s
              WHERE s.document_id = d.id AND s.is_primary IS TRUE
                AND s.deleted_at IS NULL AND s.status = 'active'
          )
        """
    )


def downgrade() -> None:
    op.drop_index("uk_kb_document_source_primary", table_name="kb_document_source", schema="oa")
    op.drop_index(
        "uk_kb_document_source_active_attachment",
        table_name="kb_document_source",
        schema="oa",
    )
    op.drop_index(
        "ix_kb_document_source_document_order",
        table_name="kb_document_source",
        schema="oa",
    )
    op.drop_table("kb_document_source", schema="oa")
