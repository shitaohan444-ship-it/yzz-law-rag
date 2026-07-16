"""MinIO client 单例（读 law-firm-files 文档原件）。"""
from minio import Minio

from app.core.config import settings

_client: Minio | None = None


def get_minio_client() -> Minio:
    """返回单例 MinIO client（懒初始化）。"""
    global _client
    if _client is None:
        _client = Minio(
            f"{settings.minio_endpoint}:{settings.minio_port}",
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_use_ssl,
        )
    return _client
