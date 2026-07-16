"""MinIO 下载封装（基于 core/minio_client 单例 client）。

逻辑移植自 law-rag-service/app/services/minio_service.py，但不 import（配置变量名不同），
改用本服务的 get_minio_client() + settings。
"""
from datetime import timedelta
from io import BytesIO

from minio.error import S3Error

from app.core.config import settings
from app.core.minio_client import get_minio_client


def download(object_key: str, bucket: str | None = None) -> bytes:
    """下载对象，返回完整 bytes（无流式版本）。"""
    client = get_minio_client()
    bucket = bucket or settings.minio_bucket
    resp = client.get_object(bucket, object_key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def file_exists(object_key: str, bucket: str | None = None) -> bool:
    """对象是否存在（NoSuchKey / NoSuchObject 视为不存在，其它 S3Error 重抛）。"""
    client = get_minio_client()
    bucket = bucket or settings.minio_bucket
    try:
        client.stat_object(bucket, object_key)
        return True
    except S3Error as e:
        if e.code in ("NoSuchKey", "NoSuchObject"):
            return False
        raise


def upload_derived(
    object_key: str,
    content: bytes,
    *,
    content_type: str,
    bucket: str | None = None,
) -> tuple[str, str]:
    """幂等写入 RAG 派生图片，返回 (bucket, object_key)。"""
    client = get_minio_client()
    bucket_name = bucket or settings.minio_bucket
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)
    if not file_exists(object_key, bucket_name):
        client.put_object(
            bucket_name,
            object_key,
            BytesIO(content),
            length=len(content),
            content_type=content_type,
        )
    return bucket_name, object_key


def presigned_url(
    object_key: str,
    *,
    bucket: str | None = None,
    expires_seconds: int | None = None,
) -> str:
    """生成预签名 GET URL（S3 风格，bucket 在路径里），对齐 Node 侧 presignedGetObject。

    默认有效期 minio_presigned_expires_seconds（3600s）。URL 在有效期内任何人持链接可取，
    调用方需自行做权限校验。
    """
    client = get_minio_client()
    bucket_name = bucket or settings.minio_bucket
    expires = timedelta(seconds=expires_seconds or settings.minio_presigned_expires_seconds)
    return client.presigned_get_object(bucket_name, object_key, expires=expires)
