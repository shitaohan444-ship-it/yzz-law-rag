"""BGE-M3 Embedding 服务（FlagEmbedding）。

单例懒加载（模型 ~2.3GB，进程级复用）；CPU forward 用锁串行化，防并发爆内存。
一次 encode 同时产出 dense(1024) + sparse(lexical_weights)，供 Milvus hybrid 检索。
"""
import threading
from time import perf_counter

from FlagEmbedding import BGEM3FlagModel

from app.core.config import settings

_model: BGEM3FlagModel | None = None
_init_lock = threading.Lock()
_encode_lock = threading.Lock()  # CPU forward 串行化


def get_embedding_model() -> BGEM3FlagModel:
    """返回单例 BGE-M3 模型（双检锁懒加载）。"""
    global _model
    if _model is None:
        with _init_lock:
            if _model is None:
                _model = BGEM3FlagModel(
                    settings.embedding_model,
                    use_fp16=settings.model_device.startswith("cuda"),
                    device=settings.model_device,
                )
    return _model


def encode_batch(
    texts: list[str],
    *,
    timings: dict[str, float] | None = None,
) -> tuple[list[list[float]], list[dict[int, float]]]:
    """批量编码，返回 (dense 向量列表, sparse 词权重列表)。

    lexical_weights 的 key 是 np.int64，必须转原生 int/float，否则 Milvus 序列化出错。
    """
    if not texts:
        return [], []
    model = get_embedding_model()
    wait_started = perf_counter()
    with _encode_lock:
        compute_started = perf_counter()
        if timings is not None:
            timings["query_embedding_lock_wait_ms"] = (
                compute_started - wait_started
            ) * 1000
        out = model.encode(
            texts,
            batch_size=settings.embedding_batch_size,
            max_length=settings.embedding_max_seq_len,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
    if timings is not None:
        timings["query_embedding_compute_ms"] = (
            perf_counter() - compute_started
        ) * 1000
    dense = out["dense_vecs"].tolist()
    sparse = [
        {int(k): float(v) for k, v in weights.items()}
        for weights in out["lexical_weights"]
    ]
    return dense, sparse
