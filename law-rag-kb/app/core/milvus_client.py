"""Milvus 客户端（pymilvus MilvusClient 新 API）。

阶段 2：单例 client + 幂等建/载 kb_chunks collection（BGE-M3 dense + sparse hybrid）。
MilvusClient 自带懒连接 grpc 通道，无需显式 connect/disconnect。
"""
from pymilvus import DataType, MilvusClient

from app.core.config import settings

# BGE-M3 dense 向量维度
_DENSE_DIM = 1024
# chunk_text 字段上限（Milvus VARCHAR max）
_CHUNK_TEXT_MAX = 65535

_client: MilvusClient | None = None


def get_milvus_client() -> MilvusClient:
    """返回单例 MilvusClient（懒初始化）。"""
    global _client
    if _client is None:
        _client = MilvusClient(
            uri=f"http://{settings.milvus_host}:{settings.milvus_port}"
        )
    return _client


def ensure_collection() -> str:
    """幂等确保 collection 存在并已 load，返回 collection 名。

    query/delete by filter 要求 collection 处于 loaded 状态，故建表后立即 load。
    dense 用 HNSW + COSINE（自文档化，不依赖 BGE-M3 已归一化的隐式假设）；
    sparse 用 SPARSE_INVERTED_INDEX + IP（BM25 风格权重，cosine 无意义）。
    """
    name = settings.milvus_collection
    client = get_milvus_client()
    if client.has_collection(name):
        client.load_collection(name)
        return name

    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=128)
    schema.add_field("doc_id", DataType.INT64)
    schema.add_field("chunk_idx", DataType.INT16)
    schema.add_field("source", DataType.VARCHAR, max_length=100)
    schema.add_field("chunk_text", DataType.VARCHAR, max_length=_CHUNK_TEXT_MAX)
    schema.add_field("dense", DataType.FLOAT_VECTOR, dim=_DENSE_DIM)
    schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
    schema.add_field("meta", DataType.JSON)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="dense",
        index_type="HNSW",
        metric_type="COSINE",
        params={"M": 16, "efConstruction": 200},
    )
    index_params.add_index(
        field_name="sparse",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="IP",
    )

    client.create_collection(
        collection_name=name, schema=schema, index_params=index_params
    )
    client.load_collection(name)
    return name
