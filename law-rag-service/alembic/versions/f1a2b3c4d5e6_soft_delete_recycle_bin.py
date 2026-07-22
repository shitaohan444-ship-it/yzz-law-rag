"""soft_delete_recycle_bin

Revision ID: f1a2b3c4d5e6
Revises: e9f0a1b2c3d4
Create Date: 2026-07-20 10:00:00

知识库文档软删除与独立回收站：
1. 普通删除改为纯软删除（status='deleted' + deleted_at），原件/图片/向量保留，可恢复。
2. 永久删除（status='purged'）才清理 MinIO/Milvus。
3. 历史已硬删的 deleted 文档（已无 MinIO/Milvus 数据）统一标记为 purged，不进入新回收站。
4. 调整公共知识库 file_hash 唯一索引：active 与 soft_deleted 附件共同占用哈希；
   回收站存在相同文件时阻止重复上传，purged 后释放哈希位允许重新上传。

upgrade 顺序严格：先回填数据（deleted→purged），再删除旧索引、按新谓词建唯一索引，
避免即将变 purged 的行在新谓词下产生重复哈希冲突。
"""
from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 历史已硬删文档（无原件/向量数据）统一标记为 purged，使其不进入新回收站。
    #    新回收站只展示 status='deleted' 的软删文档。
    op.execute(
        "UPDATE oa.kb_document SET status = 'purged', updated_at = NOW() "
        "WHERE status = 'deleted' AND deleted_at IS NOT NULL"
    )
    op.execute(
        "UPDATE oa.kb_document_source SET status = 'purged', updated_at = NOW() "
        "WHERE status = 'deleted' AND deleted_at IS NOT NULL"
    )
    op.execute(
        "UPDATE oa.sys_attachment SET status = 'purged', updated_at = NOW() "
        "WHERE biz_type = 'knowledge_base' AND status = 'inactive' "
        "AND deleted_at IS NOT NULL"
    )

    # 2) 交换 file_hash 唯一索引：按 status 占用，而非 deleted_at。
    #    active 与 soft_deleted 共同占哈希（回收站同文件阻止重复上传）；
    #    purged 落出谓词，释放哈希位允许重新上传。
    op.drop_index(
        "uk_sys_attachment_public_kb_file_hash",
        table_name="sys_attachment",
        schema="oa",
    )
    op.create_index(
        "uk_sys_attachment_public_kb_file_hash",
        "sys_attachment",
        ["file_hash"],
        unique=True,
        schema="oa",
        postgresql_where=sa.text(
            "biz_type = 'knowledge_base' AND file_hash IS NOT NULL "
            "AND status IN ('active', 'soft_deleted')"
        ),
    )


def downgrade() -> None:
    # 仅回滚索引到旧谓词。数据回填不可逆：历史 deleted 文档已无原件/向量，
    # 标记为 purged 是对其真实状态的如实记录，不还原为 deleted。
    op.drop_index(
        "uk_sys_attachment_public_kb_file_hash",
        table_name="sys_attachment",
        schema="oa",
    )
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
