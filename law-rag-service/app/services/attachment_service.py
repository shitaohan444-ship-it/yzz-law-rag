"""附件业务服务：把 MinIO 对象存储与 sys_attachment / sys_attachment_relation 业务表串联。

职责：
- upload：上传文件到 MinIO + 写 sys_attachment（bucket/object_key/etag 落库）+ 可选写关联。
- download / get_presigned_url / delete：按 attachment_id 经 object_key 操作 MinIO。
- bind_to_entity：写 sys_attachment_relation 多态关联。

约定：
- service 方法接收 session 参数（由上层 get_db 依赖或脚本显式传入），不在内部 commit；
  事务边界由调用方控制。
- storage_type 用 'minio'（与既有 'nas' 数据对称的语义码）。
- bucket/object_key/etag 来自 minio_service.upload_file 返回值；object_key 同时写入
  storage_path 以兼容 NAS 风格历史字段。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Optional, Union

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.oa_system import SysAttachment, SysAttachmentRelation
from app.services.minio_service import MinIOService, minio_service

# biz_type 语义码 → (prefix, 编号字段所在表, 编号列) 映射，用于自动解析 entity_no
_BIZ_ENTITY_MAP = {
    "case": ("cases", "case_main", "case_no"),
    "案件": ("cases", "case_main", "case_no"),
    "lead": ("leads", "crm_lead", "lead_no"),
    "线索": ("leads", "crm_lead", "lead_no"),
    "fee_agreement": ("contracts", "fin_fee_agreement", "agreement_no"),
    "收费协议": ("contracts", "fin_fee_agreement", "agreement_no"),
    "contract": ("contracts", "fin_fee_agreement", "agreement_no"),
}


class AttachmentService:
    """MinIO + sys_attachment 业务绑定服务。"""

    def __init__(self, storage: MinIOService) -> None:
        self.storage = storage

    # ------------------------------------------------------------------
    # 上传
    # ------------------------------------------------------------------
    def upload(
        self,
        session: Session,
        *,
        file_data: Union[bytes, BinaryIO, str, Path],
        filename: str,
        biz_type: str,
        biz_id: int,
        category: str,
        uploaded_by: int,
        content_type: Optional[str] = None,
        prefix: Optional[str] = None,
        entity_no: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        file_usage: Optional[int] = None,
    ) -> int:
        """上传到 MinIO + 写 sys_attachment。

        Args:
            file_data: bytes / 文件流 / 本地路径。
            filename: 原始文件名。
            biz_type: 业务对象类型语义码（case/lead/fee_agreement/...）。
            biz_id: 业务对象主键 ID。
            category: MinIO 业务分类（evidence/contract/pleading/...）。
            uploaded_by: 上传人员工 ID。
            content_type: MIME 类型；未提供则按后缀推断。
            prefix/entity_no: 显式指定 object_key 前缀与业务编号；未提供则按 biz_type 自动解析。
            entity_type/entity_id/file_usage: 提供则同步写 sys_attachment_relation 关联。

        Returns:
            新建的 sys_attachment.id。
        """
        # 1. 解析 prefix / entity_no
        if prefix is None or entity_no is None:
            auto_prefix, auto_no = self._resolve_entity_no(session, biz_type, biz_id)
            prefix = prefix or auto_prefix
            entity_no = entity_no or auto_no

        # 2. 生成 object_key 并上传
        now = datetime.now(timezone.utc)
        object_key = MinIOService.build_object_key(
            prefix,
            filename=filename,
            year=now.year,
            month=now.month,
            entity_no=entity_no,
            category=category,
        )
        result = self.storage.upload_file(object_key, file_data, content_type=content_type)

        # 3. 写 sys_attachment
        ext = Path(filename).suffix.lower().lstrip(".")
        mime = content_type or MinIOService._guess_content_type(filename) or "application/octet-stream"
        attachment = SysAttachment(
            biz_type=biz_type,
            biz_id=biz_id,
            file_name=filename,
            file_ext=ext,
            mime_type=mime,
            file_size=result["size"],
            storage_type="minio",
            storage_path=result["object_key"],        # 兼容 NAS 字段
            bucket=result["bucket"],
            object_key=result["object_key"],
            etag=result["etag"],
            original_file_name=filename,
            current_file_name=Path(result["object_key"]).name,
            uploaded_by=uploaded_by,
            uploaded_at=now,
            created_at=now,
            created_by=uploaded_by,
            updated_at=now,
            updated_by=uploaded_by,
            status="active",
            file_exists_flag="1",
            ai_index_status="pending",
        )
        session.add(attachment)
        session.flush()
        attachment_id = attachment.id

        # 4. 可选写关联
        if entity_type and entity_id is not None:
            self._add_relation(
                session, attachment_id, entity_type, entity_id,
                file_usage=file_usage, operator_id=uploaded_by,
            )
        return attachment_id

    # ------------------------------------------------------------------
    # 下载 / 预签名 / 删除
    # ------------------------------------------------------------------
    def download(self, session: Session, attachment_id: int) -> bytes:
        att = self._get_active(session, attachment_id)
        return self.storage.download_file(self._object_key_of(att))

    def get_presigned_url(self, session: Session, attachment_id: int, expires: int = 3600) -> str:
        att = self._get_active(session, attachment_id)
        return self.storage.get_presigned_url(self._object_key_of(att), expires=expires)

    def delete(self, session: Session, attachment_id: int, soft: bool = True) -> None:
        att = self._get_active(session, attachment_id)
        self.storage.delete_file(self._object_key_of(att))
        if soft:
            att.deleted_at = datetime.now(timezone.utc)
        else:
            session.delete(att)

    # ------------------------------------------------------------------
    # 多态关联
    # ------------------------------------------------------------------
    def bind_to_entity(
        self,
        session: Session,
        attachment_id: int,
        entity_type: str,
        entity_id: int,
        file_usage: Optional[int] = None,
        is_primary: int = 0,
        operator_id: Optional[int] = None,
    ) -> int:
        """写 sys_attachment_relation。返回 relation_id。"""
        return self._add_relation(
            session, attachment_id, entity_type, entity_id,
            file_usage=file_usage, is_primary=is_primary, operator_id=operator_id,
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _resolve_entity_no(self, session: Session, biz_type: str, biz_id: int) -> tuple[str, str]:
        if biz_type in _BIZ_ENTITY_MAP:
            prefix, table, col = _BIZ_ENTITY_MAP[biz_type]
            row = session.execute(
                text(f"SELECT {col} FROM oa.{table} WHERE id=:id"),
                {"id": biz_id},
            ).first()
            if row and row[0]:
                return prefix, str(row[0])
            return prefix, str(biz_id)
        return "misc", str(biz_id)

    def _add_relation(
        self, session: Session, attachment_id: int, entity_type: str, entity_id: int,
        file_usage: Optional[int], is_primary: int = 0, operator_id: Optional[int] = None,
    ) -> int:
        now = datetime.now(timezone.utc)
        rel = SysAttachmentRelation(
            attachment_id=attachment_id,
            entity_type=entity_type,
            entity_id=entity_id,
            file_usage=file_usage,
            sort_order=0,
            is_primary=is_primary,
            created_at=now,
            created_by=operator_id,
            updated_at=now,
            updated_by=operator_id,
        )
        session.add(rel)
        session.flush()
        return rel.id

    @staticmethod
    def _object_key_of(att: SysAttachment) -> str:
        # 优先新字段 object_key，回退 storage_path（兼容历史 NAS 数据）
        return att.object_key or att.storage_path

    @staticmethod
    def _get_active(session: Session, attachment_id: int) -> SysAttachment:
        att = session.get(SysAttachment, attachment_id)
        if att is None or att.deleted_at is not None:
            raise FileNotFoundError(f"附件不存在或已删除: id={attachment_id}")
        return att


# 模块级默认实例
attachment_service = AttachmentService(minio_service)
