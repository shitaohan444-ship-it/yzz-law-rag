"""add_public_kb_file_hash_unique_index

Revision ID: b6c7d8e9f0a1
Revises: a1b2c3d4e5f6
Create Date: 2026-07-16 10:00:00.000000

公共知识库上传以 SHA-256 识别完全相同的原始文件。仅约束新上传且未软删的
knowledge_base 附件；历史附件的 file_hash 为空，不受此索引影响。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uk_sys_attachment_public_kb_file_hash",
        "sys_attachment",
        ["file_hash"],
        unique=True,
        schema="oa",
        postgresql_where=sa.text(
            "biz_type = 'knowledge_base' AND file_hash IS NOT NULL "
            "AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uk_sys_attachment_public_kb_file_hash",
        table_name="sys_attachment",
        schema="oa",
    )
