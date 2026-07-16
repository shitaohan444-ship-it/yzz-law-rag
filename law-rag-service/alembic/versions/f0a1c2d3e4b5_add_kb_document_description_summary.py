"""add_kb_document_description_summary

Revision ID: f0a1c2d3e4b5
Revises: 9a7e4c2d6f10
Create Date: 2026-07-14 14:00:00.000000

为 kb_document 增加 description_summary（LLM 生成的文档级中文摘要），供 Markdown
渲染端点使用。与 content_text（原文正文）区分：content_text 是正文，description_summary
是概述。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f0a1c2d3e4b5"
down_revision: Union[str, Sequence[str], None] = "9a7e4c2d6f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kb_document",
        sa.Column(
            "description_summary",
            sa.Text(),
            nullable=True,
            comment="LLM 生成的文档级中文摘要，供 Markdown 渲染端点展示。",
        ),
        schema="oa",
    )


def downgrade() -> None:
    op.drop_column("kb_document", "description_summary", schema="oa")
