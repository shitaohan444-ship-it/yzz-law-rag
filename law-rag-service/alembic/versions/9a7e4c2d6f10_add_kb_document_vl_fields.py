"""add_kb_document_vl_fields

Revision ID: 9a7e4c2d6f10
Revises: d5e7a3b9c1f2
Create Date: 2026-07-14 11:00:00.000000

为知识库文档增加案件/卷宗通用关联和 VL 处理状态，并新增逐图分析表。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9a7e4c2d6f10"
down_revision: Union[str, Sequence[str], None] = "d5e7a3b9c1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kb_document",
        sa.Column(
            "source_type",
            sa.String(length=32),
            nullable=False,
            server_default="knowledge_base",
            comment="文档来源：knowledge_base、case_material、case_archive、other。",
        ),
        schema="oa",
    )
    op.add_column(
        "kb_document",
        sa.Column("biz_type", sa.String(length=50), nullable=True, comment="通用关联业务类型。"),
        schema="oa",
    )
    op.add_column(
        "kb_document",
        sa.Column("biz_id", sa.BigInteger(), nullable=True, comment="通用关联业务记录ID。"),
        schema="oa",
    )
    op.add_column(
        "kb_document",
        sa.Column("case_id", sa.BigInteger(), nullable=True, comment="关联案件主表ID。"),
        schema="oa",
    )
    op.add_column(
        "kb_document",
        sa.Column("dossier_no", sa.String(length=100), nullable=True, comment="案卷/卷宗编号。"),
        schema="oa",
    )
    op.add_column(
        "kb_document",
        sa.Column(
            "extra_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="知识库文档可扩展业务属性。",
        ),
        schema="oa",
    )
    op.add_column(
        "kb_document",
        sa.Column(
            "vl_status",
            sa.String(length=32),
            nullable=False,
            server_default="not_processed",
            comment="VL状态：not_processed、pending、processing、success、partial、failed。",
        ),
        schema="oa",
    )
    for column_name, comment in (
        ("image_total", "文档发现的唯一图片总数。"),
        ("image_kept", "参与RAG检索的图片数。"),
        ("image_filtered", "被过滤的装饰性图片数。"),
    ):
        op.add_column(
            "kb_document",
            sa.Column(
                column_name,
                sa.Integer(),
                nullable=False,
                server_default="0",
                comment=comment,
            ),
            schema="oa",
        )
    op.add_column(
        "kb_document",
        sa.Column("vl_processed_at", sa.DateTime(timezone=True), nullable=True, comment="最近一次VL处理完成时间。"),
        schema="oa",
    )
    op.create_foreign_key(
        "fk_kb_document_case",
        "kb_document",
        "case_main",
        ["case_id"],
        ["id"],
        source_schema="oa",
        referent_schema="oa",
        ondelete="SET NULL",
    )
    op.create_index("ix_kb_document_case_id", "kb_document", ["case_id"], schema="oa")
    op.create_index(
        "ix_kb_document_biz", "kb_document", ["biz_type", "biz_id"], schema="oa"
    )
    op.create_index("ix_kb_document_vl_status", "kb_document", ["vl_status"], schema="oa")

    op.create_table(
        "kb_document_image",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="图片分析记录主键。"),
        sa.Column("document_id", sa.BigInteger(), nullable=False, comment="关联知识库文档ID。"),
        sa.Column("attachment_id", sa.BigInteger(), nullable=True, comment="来源附件ID。"),
        sa.Column("page_no", sa.Integer(), nullable=True, comment="图片首次出现页码（从1开始）。"),
        sa.Column("page_numbers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb"), comment="图片出现的全部页码。"),
        sa.Column("image_index", sa.Integer(), nullable=False, comment="文档内图片顺序。"),
        sa.Column("image_sha256", sa.String(length=64), nullable=False, comment="图片内容SHA256。"),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("bucket_name", sa.String(length=100), nullable=True, comment="派生图片MinIO bucket。"),
        sa.Column("object_key", sa.String(length=500), nullable=True, comment="派生图片MinIO object key。"),
        sa.Column("image_category", sa.String(length=50), nullable=True),
        sa.Column("keep_for_rag", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("filter_reason", sa.String(length=500), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("description_text", sa.Text(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("vl_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("vl_model", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("remark", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["attachment_id"], ["oa.sys_attachment.id"], name="fk_kb_document_image_attachment", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["oa.kb_document.id"], name="fk_kb_document_image_document", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_kb_document_image"),
        sa.UniqueConstraint("document_id", "image_sha256", name="uk_kb_document_image_doc_hash"),
        schema="oa",
        comment="知识库文档图片提取、筛选与VL描述审计表。",
    )
    op.create_index("ix_kb_document_image_document_id", "kb_document_image", ["document_id"], schema="oa")
    op.create_index("ix_kb_document_image_vl_status", "kb_document_image", ["vl_status"], schema="oa")


def downgrade() -> None:
    op.drop_index("ix_kb_document_image_vl_status", table_name="kb_document_image", schema="oa")
    op.drop_index("ix_kb_document_image_document_id", table_name="kb_document_image", schema="oa")
    op.drop_table("kb_document_image", schema="oa")
    op.drop_index("ix_kb_document_vl_status", table_name="kb_document", schema="oa")
    op.drop_index("ix_kb_document_biz", table_name="kb_document", schema="oa")
    op.drop_index("ix_kb_document_case_id", table_name="kb_document", schema="oa")
    op.drop_constraint("fk_kb_document_case", "kb_document", schema="oa", type_="foreignkey")
    for column_name in (
        "vl_processed_at",
        "image_filtered",
        "image_kept",
        "image_total",
        "vl_status",
        "extra_metadata",
        "dossier_no",
        "case_id",
        "biz_id",
        "biz_type",
        "source_type",
    ):
        op.drop_column("kb_document", column_name, schema="oa")
