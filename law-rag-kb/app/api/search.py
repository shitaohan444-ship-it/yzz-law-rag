"""检索 API：POST /search（hybrid 召回 + bge-reranker 精排）。"""
import json
import logging
from datetime import date
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, PositiveInt

from app.core.authorization import authorized_doc_ids
from app.core.security import Principal, require_user_principal
from app.ingest import service as ingest_service
from app.rag import retrieve
from app.core.config import settings

router = APIRouter(tags=["search"])
logger = logging.getLogger("uvicorn.error")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="自然语言检索词")
    top_k: int | None = Field(None, ge=1, le=50, description="返回片段数，默认 RERANK_TOP_K")
    doc_ids: list[PositiveInt] | None = Field(
        None,
        max_length=200,
        description="限定在指定 kb_document 范围内检索；最终范围由服务端授权收窄",
    )
    category_ids: list[PositiveInt] | None = Field(None, max_length=100)
    knowledge_types: list[str] | None = Field(None, max_length=20)
    case_id_scope: PositiveInt | None = None
    effective_on: date | None = None
    effectivity_status: str | None = Field(None, max_length=20)
    cause_code: str | None = Field(None, max_length=80)
    min_score: float | None = Field(None, ge=0, le=1)


class OfficialLinkModel(BaseModel):
    provider: str
    source_name: str
    label: str
    url: str


class SearchHitModel(BaseModel):
    chunk_id: str
    doc_id: int
    doc_title: str | None
    source: str
    chunk_idx: int
    text: str
    score: float  # reranker 归一化分数 [0,1]
    article_no: str | None = None
    chapter: str | None = None
    content_type: str = "text"
    image_id: int | None = None
    page_no: int | None = None
    image_category: str | None = None
    category_id: int | None = None
    category_path: list[str] | None = None
    official_link: OfficialLinkModel | None = None


class SearchResponse(BaseModel):
    query: str
    total: int
    hits: list[SearchHitModel]


@router.post("/search", response_model=SearchResponse)
def search(
    req: SearchRequest,
    principal: Annotated[Principal, Depends(require_user_principal)],
) -> SearchResponse:
    """hybrid 召回 + bge-reranker 精排，返回相关片段与来源。

    def（非 async def）：query encode + reranker 都是 CPU-bound，由 threadpool 执行不阻塞事件循环。
    """
    total_started = perf_counter()
    timings: dict[str, float] | None = (
        {} if settings.search_timing_enabled else None
    )
    doc_scope = authorized_doc_ids(
        principal,
        req.doc_ids,
        case_id_scope=req.case_id_scope,
        category_ids=req.category_ids,
        knowledge_types=req.knowledge_types,
        effective_on=req.effective_on,
        effectivity_status=req.effectivity_status,
        cause_code=req.cause_code,
    )
    logger.info(
        "rag_search_access user_id=%s requested_docs=%s allowed_docs=%s",
        principal.user_id,
        len(req.doc_ids) if req.doc_ids is not None else "all",
        len(doc_scope) if doc_scope is not None else "all",
    )
    hits = (
        retrieve.search(req.query, doc_ids=doc_scope, top_k=req.top_k, min_score=req.min_score)
        if timings is None
        else retrieve.search(
            req.query,
            doc_ids=doc_scope,
            top_k=req.top_k,
            timings=timings,
            min_score=req.min_score,
        )
    )
    response_started = perf_counter()
    resolved_texts = ingest_service.resolve_markdown_texts([hit.text for hit in hits])
    response = SearchResponse(
        query=req.query,
        total=len(hits),
        hits=[
            SearchHitModel(
                chunk_id=h.chunk_id,
                doc_id=h.doc_id,
                doc_title=h.doc_title,
                source=h.source,
                chunk_idx=h.chunk_idx,
                text=resolved_texts[index],
                score=h.score,
                article_no=h.article_no,
                chapter=h.chapter,
                content_type=h.content_type,
                image_id=h.image_id,
                page_no=h.page_no,
                image_category=h.image_category,
                category_id=h.category_id,
                category_path=h.category_path,
                official_link=h.official_link,
            )
            for index, h in enumerate(hits)
        ],
    )
    if timings is not None:
        timings["response_build_ms"] = (perf_counter() - response_started) * 1000
        serialization_started = perf_counter()
        response.model_dump_json()
        timings["response_serialization_ms"] = (
            perf_counter() - serialization_started
        ) * 1000
        timings["total_ms"] = (perf_counter() - total_started) * 1000
        logger.info("search_timing %s", json.dumps(timings, sort_keys=True))
    return response
