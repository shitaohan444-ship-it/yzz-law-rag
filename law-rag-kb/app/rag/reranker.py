"""bge-reranker-v2-m3 精排服务（FlagEmbedding.FlagReranker）。

与 BGE-M3 embedding 同栈：复用已 pin 的 FlagEmbedding 1.2.10，不引入 sentence-transformers，
以免其与 transformers==4.44.2 的版本冲突破坏入库链。单例懒加载；CPU forward 用锁串行化，防并发爆内存。
"""
import threading
from time import perf_counter

from FlagEmbedding import FlagReranker

from app.core.config import settings

_model: FlagReranker | None = None
_init_lock = threading.Lock()
_score_lock = threading.Lock()  # CPU forward 串行化


def get_reranker_model() -> FlagReranker:
    """返回单例 FlagReranker（双检锁懒加载）。"""
    global _model
    if _model is None:
        with _init_lock:
            if _model is None:
                _model = FlagReranker(
                    settings.reranker_model,
                    use_fp16=settings.model_device.startswith("cuda"),
                    device=settings.model_device,
                )
    return _model


def rerank(
    query: str,
    texts: list[str],
    *,
    timings: dict[str, float] | None = None,
) -> list[float]:
    """对 (query, text) 对打分，返回与 texts 等长的分数列表（sigmoid 归一化到 [0,1]）。

    normalize=True 让分数可直接展示给用户；排序只看相对大小，归一化与否等价。
    """
    if not texts:
        return []
    model = get_reranker_model()
    # FlagReranker 1.2.10 不会按长度分桶；一个长摘要会让同批所有短法条都 padding
    # 到 512 token。先按长度排序并在 CPU 上小批推理，保持 max_length、模型和分数
    # 完全不变，再恢复原输入顺序。
    indexed_pairs = sorted(
        enumerate(texts), key=lambda item: len(query) + len(item[1])
    )
    pairs = [[query, text] for _, text in indexed_pairs]
    wait_started = perf_counter()
    with _score_lock:
        compute_started = perf_counter()
        if timings is not None:
            timings["reranker_lock_wait_ms"] = (
                compute_started - wait_started
            ) * 1000
        sorted_scores = model.compute_score(
            pairs,
            batch_size=settings.rerank_batch_size,
            normalize=True,
        )
    if timings is not None:
        timings["reranker_compute_ms"] = (perf_counter() - compute_started) * 1000
    # 单元素输入时 compute_score 可能退化返回 float，统一成 list
    if isinstance(sorted_scores, (int, float)):
        sorted_scores = [sorted_scores]
    scores = [0.0] * len(texts)
    for (original_index, _), score in zip(indexed_pairs, sorted_scores):
        scores[original_index] = float(score)
    return scores
