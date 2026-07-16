import os
import re
import sys
from collections import Counter

from pymilvus import MilvusClient


def first_env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return default


def field_name(field: dict) -> str:
    return str(field.get("name") or field.get("field_name") or "")


def field_type(field: dict) -> str:
    value = field.get("data_type")
    if value is None:
        value = field.get("type")
    return str(value)


print("===== R2-02 Milvus 数据快照 =====")

collection_name = first_env(
    "MILVUS_COLLECTION",
    "MILVUS_COLLECTION_NAME",
    "KB_COLLECTION_NAME",
    default="kb_chunks",
)

uri = first_env("MILVUS_URI", "MILVUS_ENDPOINT")

if not uri:
    host = first_env("MILVUS_HOST", default="standalone")
    port = first_env("MILVUS_PORT", default="19530")
    uri = f"http://{host}:{port}"

token = first_env("MILVUS_TOKEN")

try:
    if token:
        client = MilvusClient(uri=uri, token=token)
    else:
        client = MilvusClient(uri=uri)
except Exception as exc:
    print(f"[FAIL] 无法创建 MilvusClient：{type(exc).__name__}: {exc}")
    sys.exit(1)

print(f"目标 Collection：{collection_name}")
print("连接信息：已从容器环境变量读取，未输出凭据")
print()

try:
    collections = client.list_collections()
except Exception as exc:
    print(f"[FAIL] 无法列出 Collection：{type(exc).__name__}: {exc}")
    sys.exit(1)

print("===== 1. Collection 清单 =====")
for name in sorted(collections):
    print(name)

if collection_name not in collections:
    print()
    print(f"[FAIL] Collection 不存在：{collection_name}")
    sys.exit(2)

print()
print("===== 2. Collection Schema =====")

try:
    description = client.describe_collection(
        collection_name=collection_name
    )
except Exception as exc:
    print(f"[FAIL] describe_collection 失败：{type(exc).__name__}: {exc}")
    sys.exit(3)

fields = description.get("fields") or []
field_names = []

primary_field = None

for field in fields:
    name = field_name(field)
    data_type = field_type(field)
    is_primary = bool(
        field.get("is_primary")
        or field.get("is_primary_key")
    )

    if name:
        field_names.append(name)

    if is_primary:
        primary_field = name

    print(
        f"name={name}, "
        f"type={data_type}, "
        f"primary={is_primary}"
    )

if not primary_field:
    for candidate in ("chunk_id", "id"):
        if candidate in field_names:
            primary_field = candidate
            break

print()
print(f"主键字段：{primary_field or '<未识别>'}")

print()
print("===== 3. Collection 行数 =====")

try:
    stats = client.get_collection_stats(
        collection_name=collection_name
    )
except Exception as exc:
    print(f"[FAIL] get_collection_stats 失败：{type(exc).__name__}: {exc}")
    sys.exit(4)

row_count_raw = stats.get("row_count", 0)

try:
    row_count = int(row_count_raw)
except (TypeError, ValueError):
    row_count = 0

print(f"row_count={row_count}")

if row_count == 308:
    print("[PASS] row_count 与测试前参考值 308 一致")
else:
    print(
        "[WARN] row_count 与测试前参考值 308 不一致；"
        "先记录当前值，不执行清理或重建"
    )

candidate_fields = [
    "chunk_id",
    "id",
    "doc_id",
    "document_id",
    "content_type",
]

output_fields = [
    name
    for name in candidate_fields
    if name in field_names
]

if not output_fields:
    print("[FAIL] 没有识别到可用于快照的标量字段")
    sys.exit(5)

query_limit = min(
    max(row_count + 100, 1000),
    16384,
)

print()
print("===== 4. 查询全部标量记录 =====")
print(f"output_fields={','.join(output_fields)}")
print(f"query_limit={query_limit}")

try:
    rows = client.query(
        collection_name=collection_name,
        filter="",
        output_fields=output_fields,
        limit=query_limit,
    )
except Exception as exc:
    print(f"[FAIL] Milvus query 失败：{type(exc).__name__}: {exc}")
    sys.exit(6)

actual_count = len(rows)

print(f"实际返回记录数={actual_count}")

if actual_count == row_count:
    print("[PASS] 实际返回记录数与 row_count 一致")
else:
    print(
        "[WARN] 实际返回记录数与 row_count 不一致；"
        "可能与一致性级别、加载状态或查询上限有关"
    )

doc_field = None

for candidate in ("doc_id", "document_id"):
    if candidate in output_fields:
        doc_field = candidate
        break

print()
print("===== 5. 按 doc_id 统计 chunk 数 =====")

if not doc_field:
    print("[FAIL] 未识别到 doc_id 或 document_id 字段")
else:
    doc_counts = Counter(
        str(row.get(doc_field))
        for row in rows
        if row.get(doc_field) is not None
    )

    total_from_docs = 0

    def sort_key(item):
        key = item[0]
        try:
            return (0, int(key))
        except ValueError:
            return (1, key)

    for doc_id, count in sorted(
        doc_counts.items(),
        key=sort_key,
    ):
        total_from_docs += count
        print(f"doc_id={doc_id}\tchunk_count={count}")

    print(f"有 chunk 的 doc_id 数量={len(doc_counts)}")
    print(f"按 doc_id 汇总 chunk 总数={total_from_docs}")

content_type_field = (
    "content_type"
    if "content_type" in output_fields
    else None
)

print()
print("===== 6. content_type 分布 =====")

if not content_type_field:
    print("[WARN] Collection 中未发现 content_type 字段")
else:
    content_type_counts = Counter(
        str(row.get(content_type_field) or "<NULL>")
        for row in rows
    )

    for content_type, count in sorted(
        content_type_counts.items()
    ):
        print(
            f"content_type={content_type}"
            f"\tchunk_count={count}"
        )

id_field = primary_field

if not id_field or id_field not in output_fields:
    for candidate in ("chunk_id", "id"):
        if candidate in output_fields:
            id_field = candidate
            break

print()
print("===== 7. 旧 :t: / :i: Chunk ID 检查 =====")

if not id_field:
    print("[FAIL] 未识别到可检查的 chunk ID 字段")
    old_ids = []
else:
    old_ids = []

    for row in rows:
        value = row.get(id_field)

        if value is None:
            continue

        value_text = str(value)

        if re.search(r":(?:t|i):", value_text):
            old_ids.append(value_text)

    print(f"检查字段={id_field}")
    print(f"旧格式 ID 数量={len(old_ids)}")

    if not old_ids:
        print("[PASS] 未发现旧 :t: / :i: Chunk ID")
    else:
        print("[FAIL] 发现旧格式 Chunk ID")

        for value in old_ids[:100]:
            print(value)

        if len(old_ids) > 100:
            print(
                f"...共 {len(old_ids)} 条，"
                "仅显示前 100 条"
            )

print()
print("===== R2-02 执行结论 =====")

hard_failure = (
    collection_name not in collections
    or not output_fields
    or not doc_field
    or not id_field
    or len(old_ids) > 0
)

if hard_failure:
    print("R2-02 实际结果：FAIL")
    sys.exit(10)

print("R2-02 实际结果：PASS")
sys.exit(0)
