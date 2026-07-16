"""健康检查：/health 串起三基础设施连检。"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.minio_client import get_minio_client
from app.core.milvus_client import get_milvus_client

router = APIRouter()


def _check_pg() -> str:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "fail"


def _check_minio() -> str:
    try:
        client = get_minio_client()
        return "ok" if client.bucket_exists(settings.minio_bucket) else "no-bucket"
    except Exception:
        return "fail"


def _check_milvus() -> str:
    try:
        get_milvus_client().list_collections()
        return "ok"
    except Exception:
        return "fail"


def _check_model_path(model_path: str) -> str:
    """只验证离线模型目录和 config.json，不加载数 GB 模型。"""
    try:
        path = Path(model_path).expanduser()
        return "ok" if path.is_dir() and (path / "config.json").is_file() else "missing"
    except (OSError, ValueError):
        return "missing"


def _dependency_status() -> dict[str, str]:
    return {
        "pg": _check_pg(),
        "minio": _check_minio(),
        "milvus": _check_milvus(),
    }


@router.get("/health")
def health():
    """三连检：PG / MinIO / Milvus。任一 fail 仍返回 200，便于排查。"""
    return {
        **_dependency_status(),
        # 仅检查配置完整性，不发起计费的外部 VL 请求。
        "vl_configured": settings.vl_configured,
    }


@router.get("/ready")
def ready():
    """容器就绪检查：基础设施和本地模型缺一项即返回 503。"""
    dependencies = _dependency_status()
    models = {
        "embedding": _check_model_path(settings.embedding_model),
        "reranker": _check_model_path(settings.reranker_model),
    }
    auth_status = settings.auth_configuration_status
    is_ready = (
        all(value == "ok" for value in (*dependencies.values(), *models.values()))
        and auth_status != "misconfigured"
    )
    payload = {
        "status": "ready" if is_ready else "not_ready",
        **dependencies,
        "models": models,
        "authentication": auth_status,
        # 只校验配置，不调用外部计费接口，也不作为本地服务就绪门槛。
        "vl_configured": settings.vl_configured,
    }
    if not is_ready:
        return JSONResponse(status_code=503, content=payload)
    return payload
