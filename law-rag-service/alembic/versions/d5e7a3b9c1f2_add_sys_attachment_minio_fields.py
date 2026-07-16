"""add_sys_attachment_minio_fields

Revision ID: d5e7a3b9c1f2
Revises: c4a8f2e71b9d
Create Date: 2026-07-10 19:30:00.000000

MinIO 附件业务绑定：给 sys_attachment 补齐对象存储字段。
- bucket：对象存储 bucket 名（如 law-firm-files）
- object_key：对象键，下载/预签名 URL 的定位依据
- etag：对象存储返回的 etag
- 索引 ix_sys_attachment_object_key
不新增外键、不新增字典。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5e7a3b9c1f2'
down_revision: Union[str, Sequence[str], None] = 'c4a8f2e71b9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('sys_attachment',
                  sa.Column('bucket', sa.String(length=100), nullable=True,
                            comment='对象存储 bucket 名（如 law-firm-files）；NAS 场景可空'),
                  schema='oa')
    op.add_column('sys_attachment',
                  sa.Column('object_key', sa.String(length=500), nullable=True,
                            comment='对象存储对象键，下载与预签名 URL 的定位依据'),
                  schema='oa')
    op.add_column('sys_attachment',
                  sa.Column('etag', sa.String(length=128), nullable=True,
                            comment='对象存储返回的 etag，用于完整性校验'),
                  schema='oa')
    op.create_index('ix_sys_attachment_object_key', 'sys_attachment', ['object_key'], schema='oa')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_sys_attachment_object_key', table_name='sys_attachment', schema='oa')
    op.drop_column('sys_attachment', 'etag', schema='oa')
    op.drop_column('sys_attachment', 'object_key', schema='oa')
    op.drop_column('sys_attachment', 'bucket', schema='oa')
