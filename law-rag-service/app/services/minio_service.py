"""
MinIO 基础文件服务

说明：
- 本模块只负责对象存储的通用 CRUD 与 object_key 生成规则，
  不绑定 file_object / case_material / kb_document 等具体数据库表字段。
- 数据库字段最终冻结后，再在上层 service / API 中调用本模块并补索引写入。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from minio import Minio
from minio.error import S3Error

from app.core.config import settings


class MinIOService:
    """基于 MinIO 的对象存储基础服务。"""

    # 业务分类（与数据库字段解耦，上层按业务语义选用）
    CATEGORIES = frozenset(
        {
            "evidence",      # 证据
            "contract",      # 合同
            "pleading",      # 诉状/答辩状等法律文书
            "court",         # 开庭/法院相关材料
            "progress",      # 办案进展材料
            "consultation",  # 咨询记录
            "invoice",       # 发票/收据
            "agreement",     # 协议
            "other",         # 其他
        }
    )

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        secure: bool | None = None,
        bucket_name: str | None = None,
    ) -> None:
        self.endpoint = endpoint or f"{settings.minio_host}:{settings.minio_api_port}"
        self.access_key = access_key or settings.minio_root_user
        self.secret_key = secret_key or settings.minio_root_password
        self.secure = secure if secure is not None else settings.minio_secure
        self.bucket_name = bucket_name or settings.minio_bucket_name

        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
        )

    # ------------------------------------------------------------------
    # Bucket
    # ------------------------------------------------------------------
    def ensure_bucket(self, bucket_name: str | None = None) -> str:
        """
        确保 bucket 存在，不存在则创建。

        Returns:
            实际使用的 bucket 名称。
        """
        name = bucket_name or self.bucket_name
        if not self.client.bucket_exists(name):
            self.client.make_bucket(name)
        return name

    # ------------------------------------------------------------------
    # Object key 规则（与数据库字段解耦，只接受通用参数）
    # ------------------------------------------------------------------
    @staticmethod
    def _uuid8() -> str:
        """生成 8 位 UUID 前缀（取 UUID 前 8 位）。"""
        return uuid.uuid4().hex[:8]

    @staticmethod
    def _timestamp() -> str:
        """生成 yyyyMMddHHmmss 时间戳。"""
        return datetime.now().strftime("%Y%m%d%H%M%S")

    @classmethod
    def build_object_key(
        cls,
        prefix: str,
        *,
        filename: str,
        year: int | None = None,
        month: int | None = None,
        entity_no: str | None = None,
        category: str | None = None,
        temp: bool = False,
    ) -> str:
        """
        按规则生成 object_key。

        规则：
          - cases/{year}/{month}/{case_no}/{category}/{yyyyMMddHHmmss}_{uuid8}_{filename}
          - leads/{year}/{month}/{lead_no}/{category}/{yyyyMMddHHmmss}_{uuid8}_{filename}
          - contracts/{year}/{month}/{agreement_no}/{category}/{yyyyMMddHHmmss}_{uuid8}_{filename}
          - temp/{yyyyMMdd}/{uuid8}_{filename}

        Args:
            prefix: 顶层前缀，例如 "cases" / "leads" / "contracts" / "temp"。
            filename: 原始文件名。
            year: 年份（cases / leads / contracts 用）。
            month: 月份（cases / leads / contracts 用）。
            entity_no: 业务编号（case_no / lead_no / agreement_no 等）。
            category: 业务分类，见 MinIOService.CATEGORIES。
            temp: 是否为临时文件，为 True 时走 temp/ 规则。

        Returns:
            符合 MinIO 规范的 object_key。
        """
        if temp:
            today = datetime.now().strftime("%Y%m%d")
            return f"temp/{today}/{cls._uuid8()}_{filename}"

        # 常规业务文件：year / month / entity_no / category 必须存在
        if year is None or month is None:
            raise ValueError("非 temp 模式下 year 和 month 必须提供")
        if not entity_no:
            raise ValueError("非 temp 模式下 entity_no 必须提供")
        if not category:
            raise ValueError("非 temp 模式下 category 必须提供")
        if category not in cls.CATEGORIES:
            raise ValueError(
                f"category 必须是 {sorted(cls.CATEGORIES)} 之一，收到: {category}"
            )

        month_str = f"{month:02d}"
        key = (
            f"{prefix}/{year}/{month_str}/{entity_no}/{category}/"
            f"{cls._timestamp()}_{cls._uuid8()}_{filename}"
        )
        return key

    # ------------------------------------------------------------------
    # Upload / Download / Presigned URL / Delete / Exists
    # ------------------------------------------------------------------
    def upload_file(
        self,
        object_key: str,
        data: bytes | BinaryIO | str | Path,
        content_type: str | None = None,
        bucket_name: str | None = None,
        overwrite: bool = False,
    ) -> dict:
        """
        上传文件到 MinIO。

        Args:
            object_key: 对象键。
            data: bytes、文件流、本地文件路径或 Path。
            content_type: MIME 类型；未提供时根据后缀自动推断。
            bucket_name: 目标 bucket，默认使用配置 bucket。
            overwrite: 是否允许覆盖同名对象，默认 False。

        Returns:
            包含 bucket、object_key、etag、size 的字典。

        Raises:
            FileExistsError: 对象已存在且 overwrite=False 时抛出。
        """
        bucket = bucket_name or self.bucket_name
        self.ensure_bucket(bucket)

        if not overwrite and self.file_exists(object_key, bucket):
            raise FileExistsError(
                f"对象已存在，禁止覆盖: bucket={bucket}, object_key={object_key}"
            )

        if isinstance(data, (str, Path)):
            file_path = Path(data)
            length = file_path.stat().st_size
            data_stream: BinaryIO = file_path.open("rb")
            if content_type is None:
                content_type = self._guess_content_type(file_path.name)
        elif isinstance(data, bytes):
            length = len(data)
            data_stream = BytesIO(data)
        else:
            # 假设为 BinaryIO
            data.seek(0, 2)
            length = data.tell()
            data.seek(0)
            data_stream = data

        try:
            result = self.client.put_object(
                bucket,
                object_key,
                data_stream,
                length,
                content_type=content_type or "application/octet-stream",
            )
        finally:
            # 仅在我们打开文件句柄时才关闭
            if isinstance(data, (str, Path)):
                data_stream.close()

        return {
            "bucket": bucket,
            "object_key": object_key,
            "etag": result.etag,
            "size": length,
        }

    def download_file(
        self,
        object_key: str,
        bucket_name: str | None = None,
    ) -> bytes:
        """
        从 MinIO 下载文件内容并返回 bytes。

        Args:
            object_key: 对象键。
            bucket_name: 目标 bucket。

        Returns:
            文件二进制内容。
        """
        bucket = bucket_name or self.bucket_name
        response = self.client.get_object(bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def get_presigned_url(
        self,
        object_key: str,
        expires: int = 3600,
        method: str = "GET",
        bucket_name: str | None = None,
    ) -> str:
        """
        生成预签名 URL。

        Args:
            object_key: 对象键。
            expires: 有效期（秒），默认 1 小时。
            method: HTTP 方法，GET 或 PUT。
            bucket_name: 目标 bucket。

        Returns:
            预签名 URL 字符串。
        """
        from datetime import timedelta

        bucket = bucket_name or self.bucket_name
        delta = timedelta(seconds=expires)
        if method.upper() == "GET":
            return self.client.presigned_get_object(bucket, object_key, expires=delta)
        if method.upper() == "PUT":
            return self.client.presigned_put_object(bucket, object_key, expires=delta)
        raise ValueError(f"不支持的预签名方法: {method}")

    def delete_file(
        self,
        object_key: str,
        bucket_name: str | None = None,
    ) -> None:
        """
        删除 MinIO 中的对象。

        Args:
            object_key: 对象键。
            bucket_name: 目标 bucket。
        """
        bucket = bucket_name or self.bucket_name
        self.client.remove_object(bucket, object_key)

    def file_exists(
        self,
        object_key: str,
        bucket_name: str | None = None,
    ) -> bool:
        """
        检查对象是否存在。

        Args:
            object_key: 对象键。
            bucket_name: 目标 bucket。

        Returns:
            True 表示存在，False 表示不存在。
        """
        bucket = bucket_name or self.bucket_name
        try:
            self.client.stat_object(bucket, object_key)
            return True
        except S3Error as exc:
            if exc.code in ("NoSuchKey", "NoSuchObject"):
                return False
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _guess_content_type(filename: str) -> str | None:
        """根据文件名后缀猜测 MIME 类型。"""
        suffix = Path(filename).suffix.lower()
        mapping = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            ".xls": "application/vnd.ms-excel",
            ".xlsx": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            ".ppt": "application/vnd.ms-powerpoint",
            ".pptx": (
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ),
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".zip": "application/zip",
        }
        return mapping.get(suffix)


# 全局默认实例，方便上层直接导入使用
minio_service = MinIOService()
