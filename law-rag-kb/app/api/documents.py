"""文档入库 API：POST /documents/{doc_id}/ingest、GET /documents/{doc_id}。"""
import dataclasses
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from app.core.authorization import can_access_document
from app.core.security import Principal, require_service_principal, require_user_principal
from app.ingest import service as ingest_service

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger("uvicorn.error")


class SourcePromotionRequest(BaseModel):
    target_doc_id: int = Field(gt=0)
    source_id: int = Field(gt=0)
    mode: str = Field(pattern="^(append|replace)$")
    source_title: str | None = Field(default=None, max_length=255)


class SourceRebuildItem(BaseModel):
    source_id: int = Field(gt=0)
    staging_doc_id: int = Field(gt=0)


class SourcesRebuildRequest(BaseModel):
    target_doc_id: int = Field(gt=0)
    items: list[SourceRebuildItem] = Field(min_length=1, max_length=100)


@router.post("/{doc_id}/ingest")
def ingest(
    doc_id: Annotated[int, Path(gt=0)],
    _principal: Annotated[Principal, Depends(require_service_principal)],
    force: bool = False,
):
    """同步入库一个 kb_document。

    def（非 async def）：BGE-M3 CPU 编码是 CPU-bound，async 会阻塞事件循环；
    普通函数由 Starlette 扔进 threadpool 跑，不卡 /health 等其它请求。
    """
    try:
        result = ingest_service.ingest_document(doc_id, force=force)
    except ingest_service.DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="kb_document not found") from None
    return dataclasses.asdict(result)


@router.post("/{staging_doc_id}/promote")
def promote(
    staging_doc_id: Annotated[int, Path(gt=0)],
    target_doc_id: Annotated[int, Query(gt=0)],
    _principal: Annotated[Principal, Depends(require_service_principal)],
):
    """把已成功入库的隐藏 staging 文档安全提升到原文档 ID。"""
    try:
        result = ingest_service.promote_staging_document(
            staging_doc_id, target_doc_id
        )
    except ingest_service.DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="kb_document not found") from None
    except ingest_service.DocumentPromotionError:
        raise HTTPException(status_code=409, detail="document promotion rejected") from None
    return dataclasses.asdict(result)


@router.post("/{staging_doc_id}/promote-source")
def promote_source(
    staging_doc_id: Annotated[int, Path(gt=0)],
    req: SourcePromotionRequest,
    _principal: Annotated[Principal, Depends(require_service_principal)],
):
    """把 staging 文档安全追加或替换为目标文档的一个来源。"""
    from app.ingest import sources as source_service

    try:
        result = source_service.promote_staging_source(
            staging_doc_id,
            req.target_doc_id,
            req.source_id,
            mode=req.mode,
            source_title=req.source_title,
        )
    except ingest_service.DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="kb_document not found") from None
    except source_service.SourcePromotionError:
        raise HTTPException(status_code=409, detail="source promotion rejected") from None
    return dataclasses.asdict(result)


@router.post("/rebuild-sources")
def rebuild_sources(
    req: SourcesRebuildRequest,
    _principal: Annotated[Principal, Depends(require_service_principal)],
):
    """全部来源成功后，原子替换目标文档的完整 Chunk 集合。"""
    from app.ingest import sources as source_service

    try:
        result = source_service.rebuild_from_staging_sources(
            req.target_doc_id,
            [(item.source_id, item.staging_doc_id) for item in req.items],
        )
    except ingest_service.DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="kb_document not found") from None
    except source_service.SourcePromotionError:
        raise HTTPException(status_code=409, detail="source rebuild rejected") from None
    return dataclasses.asdict(result)


@router.delete("/{staging_doc_id}/staging")
def cleanup_staging(
    staging_doc_id: Annotated[int, Path(gt=0)],
    _principal: Annotated[Principal, Depends(require_service_principal)],
):
    """清理替换失败后残留的 staging 文档、Chunk 与对象。"""
    ingest_service.cleanup_staging_document(staging_doc_id)
    return {"status": "cleaned"}


@router.get("/{doc_id}")
def get_status(
    doc_id: Annotated[int, Path(gt=0)],
    principal: Annotated[Principal, Depends(require_user_principal)],
):
    """查询入库状态 + 实时切片数（从 Milvus 查）。"""
    if not can_access_document(principal, doc_id):
        logger.info(
            "rag_document_access decision=deny user_id=%s doc_id=%s endpoint=status",
            principal.user_id,
            doc_id,
        )
        raise HTTPException(status_code=404, detail="kb_document not found")
    logger.info(
        "rag_document_access decision=allow user_id=%s doc_id=%s endpoint=status",
        principal.user_id,
        doc_id,
    )
    status = ingest_service.get_document_status(doc_id)
    if status is None:
        raise HTTPException(status_code=404, detail="kb_document not found")
    return dataclasses.asdict(status)


@router.get("/{doc_id}/markdown")
def get_markdown(
    doc_id: Annotated[int, Path(gt=0)],
    principal: Annotated[Principal, Depends(require_user_principal)],
    source_id: Annotated[int | None, Query(gt=0)] = None,
):
    """渲染文档为 Markdown：标题 + LLM 概述 + 轻量结构化正文 + 附图（MinIO 预签名链接）。

    预签名图片链接现场生成（默认 300s 有效）；正文从 content_text 或 MinIO 原件取。
    """
    if not can_access_document(principal, doc_id):
        logger.info(
            "rag_document_access decision=deny user_id=%s doc_id=%s endpoint=markdown",
            principal.user_id,
            doc_id,
        )
        raise HTTPException(status_code=404, detail="kb_document not found")
    logger.info(
        "rag_document_access decision=allow user_id=%s doc_id=%s endpoint=markdown",
        principal.user_id,
        doc_id,
    )
    rendered = ingest_service.build_document_markdown(doc_id, source_id=source_id)
    if rendered is None:
        raise HTTPException(status_code=404, detail="kb_document not found")
    return dataclasses.asdict(rendered)


@router.get("/{doc_id}/chunks")
def get_chunks(
    doc_id: Annotated[int, Path(gt=0)],
    principal: Annotated[Principal, Depends(require_user_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    source_id: Annotated[int | None, Query(gt=0)] = None,
):
    """分页返回文档 Chunk，不读取或返回 dense/sparse 向量。"""
    if not can_access_document(principal, doc_id):
        logger.info(
            "rag_document_access decision=deny user_id=%s doc_id=%s endpoint=chunks",
            principal.user_id,
            doc_id,
        )
        raise HTTPException(status_code=404, detail="kb_document not found")
    try:
        result = ingest_service.get_document_chunks(
            doc_id, page=page, page_size=page_size, source_id=source_id
        )
    except ingest_service.DocumentChunksUnavailableError:
        raise HTTPException(status_code=502, detail="chunk service unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="kb_document not found")
    return dataclasses.asdict(result)
