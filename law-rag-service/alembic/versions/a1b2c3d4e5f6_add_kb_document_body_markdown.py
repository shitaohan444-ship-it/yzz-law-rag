"""add_kb_document_body_markdown

Revision ID: a1b2c3d4e5f6
Revises: f0a1c2d3e4b5
Create Date: 2026-07-14 15:00:00.000000

为 kb_document 增加 body_markdown：统一切片流水线下，文档转成的规范 Markdown
全文（含 #img:{image_id} 图片占位符）。供渲染端点与重切复用，避免重复解析原件。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f0a1c2d3e4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kb_document",
        sa.Column(
            "body_markdown",
            sa.Text(),
            nullable=True,
            comment="文档转成的规范 Markdown 全文（含 #img:{image_id} 占位），供渲染与切片。",
        ),
        schema="oa",
    )


def downgrade() -> None:
    op.drop_column("kb_document", "body_markdown", schema="oa")
