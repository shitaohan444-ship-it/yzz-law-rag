"""add legal regulation catalog and official-link mappings

Revision ID: b4c5d6e7f8a9
Revises: a2b3c4d5e6f7
Create Date: 2026-07-31 11:30:00

Only additive PostgreSQL objects are introduced.  Knowledge documents, chunks,
MinIO objects and Milvus data are deliberately untouched.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b4c5d6e7f8a9"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_regulation_import_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("execution_mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "statistics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "report_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "execution_mode IN ('apply')",
            name="ck_legal_regulation_import_run_mode",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'failed')",
            name="ck_legal_regulation_import_run_status",
        ),
        sa.CheckConstraint(
            "source_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_legal_regulation_import_run_sha256",
        ),
        schema="oa",
    )
    op.create_index(
        "idx_legal_regulation_import_run_sha",
        "legal_regulation_import_run",
        ["provider", "source_sha256", "started_at"],
        schema="oa",
    )

    op.create_table(
        "legal_regulation_catalog",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=32), nullable=False),
        sa.Column("regulation_name", sa.String(length=500), nullable=False),
        sa.Column("normalized_name", sa.String(length=500), nullable=False),
        sa.Column("regulation_category", sa.String(length=64), nullable=False),
        sa.Column("official_url", sa.Text(), nullable=False),
        sa.Column("promulgation_date", sa.Date(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("effectivity_status", sa.String(length=64), nullable=True),
        sa.Column("issuing_authority", sa.String(length=500), nullable=True),
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_seen_run_id", sa.BigInteger(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_run_id"],
            ["oa.legal_regulation_import_run.id"],
            name="fk_legal_regulation_catalog_last_seen_run",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "provider",
            "external_id",
            name="uk_legal_regulation_catalog_provider_external",
        ),
        sa.UniqueConstraint(
            "official_url",
            name="uk_legal_regulation_catalog_official_url",
        ),
        sa.CheckConstraint(
            "external_id ~ '^[0-9a-f]{32}$'",
            name="ck_legal_regulation_catalog_external_id",
        ),
        sa.CheckConstraint(
            "official_url ~ '^https://flk\\.npc\\.gov\\.cn/detail\\?id=[0-9a-f]{32}$'",
            name="ck_legal_regulation_catalog_official_url",
        ),
        schema="oa",
    )
    op.create_index(
        "idx_legal_regulation_catalog_match",
        "legal_regulation_catalog",
        ["provider", "regulation_category", "normalized_name"],
        schema="oa",
    )
    op.create_index(
        "idx_legal_regulation_catalog_current",
        "legal_regulation_catalog",
        ["provider", "is_current"],
        schema="oa",
    )

    op.create_table(
        "kb_document_regulation_link",
        sa.Column("document_id", sa.BigInteger(), primary_key=True),
        sa.Column("catalog_id", sa.BigInteger(), nullable=False),
        sa.Column("match_method", sa.String(length=40), nullable=False),
        sa.Column(
            "version_semantics",
            sa.String(length=48),
            nullable=False,
            server_default="latest_official_by_title",
        ),
        sa.Column("linked_run_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["oa.kb_document.id"],
            name="fk_kb_document_regulation_link_document",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_id"],
            ["oa.legal_regulation_catalog.id"],
            name="fk_kb_document_regulation_link_catalog",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["linked_run_id"],
            ["oa.legal_regulation_import_run.id"],
            name="fk_kb_document_regulation_link_run",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "match_method IN ('normalized_title', 'copy_suffix', 'latest_by_date')",
            name="ck_kb_document_regulation_link_match_method",
        ),
        sa.CheckConstraint(
            "version_semantics = 'latest_official_by_title'",
            name="ck_kb_document_regulation_link_version_semantics",
        ),
        schema="oa",
    )
    op.create_index(
        "idx_kb_document_regulation_link_catalog",
        "kb_document_regulation_link",
        ["catalog_id"],
        schema="oa",
    )
    op.create_index(
        "idx_kb_document_regulation_link_run",
        "kb_document_regulation_link",
        ["linked_run_id"],
        schema="oa",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_kb_document_regulation_link_run",
        table_name="kb_document_regulation_link",
        schema="oa",
    )
    op.drop_index(
        "idx_kb_document_regulation_link_catalog",
        table_name="kb_document_regulation_link",
        schema="oa",
    )
    op.drop_table("kb_document_regulation_link", schema="oa")
    op.drop_index(
        "idx_legal_regulation_catalog_current",
        table_name="legal_regulation_catalog",
        schema="oa",
    )
    op.drop_index(
        "idx_legal_regulation_catalog_match",
        table_name="legal_regulation_catalog",
        schema="oa",
    )
    op.drop_table("legal_regulation_catalog", schema="oa")
    op.drop_index(
        "idx_legal_regulation_import_run_sha",
        table_name="legal_regulation_import_run",
        schema="oa",
    )
    op.drop_table("legal_regulation_import_run", schema="oa")
