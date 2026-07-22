"""Hybrid 检索链：query 编码 → dense+sparse 并行召回 → RRFRanker 融合 → bge-reranker 精排。

与入库链共用同一 BGE-M3 模型（query/doc 同模型，保证向量空间一致）。
检索编排为纯函数，不引入 LangGraph（留阶段 4 生成链再上状态机）。
"""
from dataclasses import dataclass
import re
from time import perf_counter

from pymilvus import AnnSearchRequest, RRFRanker, WeightedRanker

from app.core.config import settings
from app.core.milvus_client import ensure_collection, get_milvus_client
from app.ingest import embedding
from app.rag import reranker
from app.rag.category_resolver import resolve_document_categories

# sparse 检索丢弃高频词权重比例（与 BGE-M3 官方推荐一致）
_SPARSE_DROP_RATIO = 0.2

# 口语制造主体统一到法律文本常用的“生产者”。只用于 reranker 查询侧，召回仍使用
# 用户原问题，避免改写损失 dense/sparse 召回信息。
_MANUFACTURER_SYNONYM_RE = re.compile(
    r"(?:生产厂家|生产厂商|生产商|制造商|厂家|厂商)"
)
_LIABILITY_INTENT_REPLACEMENTS = (
    (
        re.compile(
            r"(?:(?:是否|要不要|需不需要|应不应当)赔(?:偿)?(?:吗)?|要赔(?:偿)?吗)"
            r"(?!哪些|什么|多少|范围|项目|费用)"
        ),
        "承担侵权责任",
    ),
    (
        re.compile(r"(?:是否|要不要|需不需要|应不应当)负责(?:吗)?"),
        "承担侵权责任",
    ),
    (re.compile(r"谁负责"), "谁承担侵权责任"),
    (re.compile(r"承担(?:什么|何种)责任"), "承担侵权责任"),
    (re.compile(r"可以找生产者(?:吗)?"), "生产者承担侵权责任"),
)


@dataclass
class SearchHit:
    chunk_id: str
    doc_id: int
    doc_title: str | None
    source: str
    chunk_idx: int
    text: str
    score: float  # reranker 归一化分数 [0,1]
    article_no: str | None = None  # 阶段6：条款号（如"第十九条"），递归切片时为 None
    chapter: str | None = None  # 阶段6：所属章节
    content_type: str = "text"
    image_id: int | None = None
    page_no: int | None = None
    image_category: str | None = None
    category_id: int | None = None
    category_path: list[str] | None = None


def search(
    query: str,
    *,
    doc_ids: list[int] | None = None,
    top_k: int | None = None,
    timings: dict[str, float] | None = None,
) -> list[SearchHit]:
    """检索编排：hybrid 召回 → reranker 精排 → 返回 top_k 片段（含来源）。

    top_k 默认 settings.rerank_top_k（精排后返回数）。
    召回候选池取 max(search_top_k, top_k)，保证 reranker 有足够候选。
    """
    total_started = perf_counter()
    # [] 是“已授权但无可见文档”，绝不能退化为无过滤全库检索。
    if doc_ids is not None and not doc_ids:
        if timings is not None:
            timings["retrieve_total_ms"] = (perf_counter() - total_started) * 1000
        return []
    rerank_top = top_k if top_k is not None else settings.rerank_top_k
    recall_k = max(settings.search_top_k, rerank_top)

    hits = (
        hybrid_recall(query, limit=recall_k, doc_ids=doc_ids)
        if timings is None
        else hybrid_recall(
            query, limit=recall_k, doc_ids=doc_ids, timings=timings
        )
    )
    if not hits:
        if timings is not None:
            timings["retrieve_total_ms"] = (perf_counter() - total_started) * 1000
        return []

    rerank_query = normalize_legal_query(query)
    scores = (
        reranker.rerank(rerank_query, [h.text for h in hits])
        if timings is None
        else reranker.rerank(
            rerank_query,
            [h.text for h in hits],
            timings=timings,
        )
    )
    ranked = sorted(zip(hits, scores), key=lambda x: x[1], reverse=True)
    # 阶段6：阈值过滤弱相关片段（score < rerank_min_score），保底留 top-1 防空结果
    if settings.rerank_min_score > 0:
        kept = [rh for rh in ranked if rh[1] >= settings.rerank_min_score]
        ranked = kept or ranked[:1]

    result = [
        SearchHit(
            chunk_id=h.chunk_id,
            doc_id=h.doc_id,
            doc_title=(h.meta or {}).get("doc_title"),
            source=h.source,
            chunk_idx=h.chunk_idx,
            text=h.text,
            score=float(s),
            article_no=(h.meta or {}).get("article_no"),
            chapter=(h.meta or {}).get("chapter"),
            content_type=(h.meta or {}).get("content_type") or "text",
            image_id=(h.meta or {}).get("image_id"),
            page_no=(h.meta or {}).get("page_no"),
            image_category=(h.meta or {}).get("image_category"),
            category_id=(h.meta or {}).get("category_id"),
            category_path=(h.meta or {}).get("category_path"),
        )
        for h, s in ranked[:rerank_top]
    ]
    categories = resolve_document_categories([hit.doc_id for hit in result])
    for hit in result:
        category = categories.get(hit.doc_id)
        if category is not None:
            hit.doc_title = category.doc_title
            hit.source = category.name
            hit.category_id = category.category_id
            hit.category_path = category.path
    if timings is not None:
        timings["retrieve_total_ms"] = (perf_counter() - total_started) * 1000
    return result


def normalize_legal_query(query: str) -> str:
    """归一化法律口语中的主体和直接责任意图，供通用 Reranker 使用。

    不包含文档、chunk、条号或完整测试问题等数据特例；“赔哪些费用”等损害范围
    问题不会被改写，只有明确的是否担责/谁担责意图才补齐“承担侵权责任”。
    """
    value = re.sub(r"\s+", " ", query or "").strip()
    value = _MANUFACTURER_SYNONYM_RE.sub("生产者", value)
    for pattern, replacement in _LIABILITY_INTENT_REPLACEMENTS:
        value = pattern.sub(replacement, value)
    return value


@dataclass
class _RecallHit:
    """Milvus 召回原始结果（内部用，distance 为 RRF 融合分仅作调试）。"""

    chunk_id: str
    doc_id: int
    chunk_idx: int
    source: str
    text: str
    meta: dict
    distance: float


def hybrid_recall(
    query: str,
    *,
    limit: int,
    doc_ids: list[int] | None = None,
    timings: dict[str, float] | None = None,
) -> list[_RecallHit]:
    """dense(HNSW+COSINE) + sparse(SPARSE_INVERTED+IP) 并行召回，RRFRanker 融合返回 limit 条。"""
    if doc_ids is not None and not doc_ids:
        return []
    ensure_collection()

    embedding_started = perf_counter()
    dense_vec, sparse_vec = (
        embedding.encode_batch([query])
        if timings is None
        else embedding.encode_batch([query], timings=timings)
    )
    if timings is not None:
        timings["query_embedding_ms"] = (
            perf_counter() - embedding_started
        ) * 1000
    expr = _build_doc_filter(doc_ids)

    dense_req = AnnSearchRequest(
        data=[dense_vec[0]],
        anns_field="dense",
        param={"metric_type": "COSINE", "params": {"ef": settings.hnsw_ef}},
        limit=limit,
        expr=expr,
    )
    sparse_req = AnnSearchRequest(
        data=[sparse_vec[0]],
        anns_field="sparse",
        param={
            "metric_type": "IP",
            "params": {"drop_ratio_search": _SPARSE_DROP_RATIO},
        },
        limit=limit,
        expr=expr,
    )

    client = get_milvus_client()
    if settings.hybrid_ranker == "weighted":
        ranker = WeightedRanker(settings.dense_weight, settings.sparse_weight)
    else:
        ranker = RRFRanker(k=settings.rrf_k)
    hybrid_started = perf_counter()
    res = client.hybrid_search(
        collection_name=settings.milvus_collection,
        reqs=[dense_req, sparse_req],
        ranker=ranker,
        limit=limit,
        output_fields=["doc_id", "chunk_idx", "source", "chunk_text", "meta"],
    )
    if timings is not None:
        # pymilvus 在服务端把 dense/sparse ANN 与 RRF 作为一个原子 RPC 执行，客户端
        # 无法无侵入拆分三段；详细单路诊断由 scripts/profile_search.py 提供。
        timings["dense_sparse_search_rrf_ms"] = (
            perf_counter() - hybrid_started
        ) * 1000
    # MilvusClient.hybrid_search 单 query 返回 List[dict]；防御性处理个别版本嵌套
    rows = res[0] if res and isinstance(res[0], list) else res
    return [_to_hit(r) for r in rows]


def _build_doc_filter(doc_ids: list[int] | None) -> str | None:
    """构造 doc_id in [...] 过滤表达式（doc_ids 全为 int，直接 str 安全）。"""
    if doc_ids is None:
        return None
    return f"doc_id in {list(doc_ids)}"


def _to_hit(row: dict) -> _RecallHit:
    # MilvusClient 返回扁平 dict（id/distance 在顶层，output_fields 也在顶层）；
    # 兼容个别版本把字段包在 entity 下
    e = row.get("entity", row)
    return _RecallHit(
        chunk_id=row.get("id", "") or "",
        doc_id=int(e.get("doc_id") or 0),
        chunk_idx=int(e.get("chunk_idx") or 0),
        source=str(e.get("source") or ""),
        text=str(e.get("chunk_text") or ""),
        meta=e.get("meta") or {},
        distance=float(row.get("distance") or 0.0),
    )
