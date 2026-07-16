import json
import os
import sys
import time
from collections import Counter

from pymilvus import MilvusClient


def env_first(*names, default=None):
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return default


def parse_meta(value):
    if isinstance(value, dict):
        return value

    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    return {}


collection = env_first(
    "MILVUS_COLLECTION",
    "MILVUS_COLLECTION_NAME",
    "KB_COLLECTION_NAME",
    default="kb_chunks",
)

uri = env_first("MILVUS_URI", "MILVUS_ENDPOINT")

if not uri:
    host = env_first("MILVUS_HOST", default="standalone")
    port = env_first("MILVUS_PORT", default="19530")
    uri = f"http://{host}:{port}"

token = env_first("MILVUS_TOKEN")

client = (
    MilvusClient(uri=uri, token=token)
    if token
    else MilvusClient(uri=uri)
)

print("===== R2-02B MILVUS COUNT DIAGNOSTIC =====")
print(f"collection={collection}")
print()

print("===== 1. REPEATED COLLECTION STATS =====")

stats_values = []

for index in range(3):
    stats = client.get_collection_stats(
        collection_name=collection
    )

    value = int(stats.get("row_count", 0))
    stats_values.append(value)

    print(f"stats_round_{index + 1}={value}")

    if index < 2:
        time.sleep(1)

print(f"stats_stable={len(set(stats_values)) == 1}")
print()

print("===== 2. COLLECTION LOAD STATE =====")

try:
    load_state = client.get_load_state(
        collection_name=collection
    )
    print(json.dumps(load_state, ensure_ascii=True, default=str))
except Exception as exc:
    print(
        "load_state_error="
        f"{type(exc).__name__}:{exc}"
    )

print()
print("===== 3. AGGREGATE COUNT =====")

aggregate_count = None

try:
    result = client.query(
        collection_name=collection,
        filter="",
        output_fields=["count(*)"],
        consistency_level="Strong",
    )

    print(
        "aggregate_raw="
        + json.dumps(
            result,
            ensure_ascii=True,
            default=str,
        )
    )

    if result:
        first = result[0]

        for key in (
            "count(*)",
            "count",
            "COUNT(*)",
        ):
            if key in first:
                aggregate_count = int(first[key])
                break

    print(f"aggregate_count={aggregate_count}")
except Exception as exc:
    print(
        "aggregate_error="
        f"{type(exc).__name__}:{exc}"
    )

print()
print("===== 4. STRONG CONSISTENCY ENTITY QUERY =====")

query_kwargs = dict(
    collection_name=collection,
    filter="",
    output_fields=[
        "id",
        "doc_id",
        "chunk_idx",
        "meta",
    ],
    limit=16384,
)

try:
    rows = client.query(
        **query_kwargs,
        consistency_level="Strong",
    )
    print("query_consistency=Strong")
except Exception as exc:
    print(
        "strong_query_error="
        f"{type(exc).__name__}:{exc}"
    )

    rows = client.query(**query_kwargs)
    print("query_consistency=default_fallback")

print(f"live_query_count={len(rows)}")

ids = [
    str(row.get("id"))
    for row in rows
    if row.get("id") is not None
]

unique_ids = set(ids)

missing_id_count = sum(
    1
    for row in rows
    if row.get("id") is None
)

missing_doc_id_count = sum(
    1
    for row in rows
    if row.get("doc_id") is None
)

duplicate_id_count = len(ids) - len(unique_ids)

print(f"id_count={len(ids)}")
print(f"unique_id_count={len(unique_ids)}")
print(f"duplicate_id_count={duplicate_id_count}")
print(f"missing_id_count={missing_id_count}")
print(f"missing_doc_id_count={missing_doc_id_count}")

print()
print("===== 5. DOC COUNTS =====")

doc_counts = Counter(
    str(row.get("doc_id"))
    for row in rows
    if row.get("doc_id") is not None
)

for doc_id, count in sorted(
    doc_counts.items(),
    key=lambda item: (
        0,
        int(item[0]),
    )
    if item[0].isdigit()
    else (
        1,
        item[0],
    ),
):
    print(f"doc_id={doc_id}\tcount={count}")

print(f"document_count={len(doc_counts)}")
print(f"document_chunk_sum={sum(doc_counts.values())}")

print()
print("===== 6. META CONTENT TYPE DISTRIBUTION =====")

content_types = Counter()
meta_parse_failures = 0
meta_missing_count = 0

for row in rows:
    raw_meta = row.get("meta")

    if raw_meta in (None, "", {}):
        meta_missing_count += 1
        continue

    meta = parse_meta(raw_meta)

    if not meta:
        meta_parse_failures += 1
        continue

    content_type = (
        meta.get("content_type")
        or meta.get("type")
        or meta.get("chunk_type")
        or "<NOT_SET>"
    )

    content_types[str(content_type)] += 1

print(f"meta_missing_count={meta_missing_count}")
print(f"meta_parse_failure_count={meta_parse_failures}")

for content_type, count in sorted(
    content_types.items()
):
    print(
        f"content_type={content_type}"
        f"\tcount={count}"
    )

print()
print("===== 7. OLD ID AND ID FORMAT CHECK =====")

old_ids = [
    value
    for value in ids
    if ":t:" in value or ":i:" in value
]

print(f"old_t_i_id_count={len(old_ids)}")

prefix_counts = Counter()

for value in ids:
    parts = value.split(":")

    if len(parts) >= 2:
        prefix = ":".join(parts[:2])
    else:
        prefix = "<NO_COLON>"

    prefix_counts[prefix] += 1

for prefix, count in prefix_counts.most_common(20):
    print(f"id_prefix={prefix}\tcount={count}")

print()
print("===== 8. COUNT COMPARISON =====")

stats_count = stats_values[-1]
live_count = len(rows)
delta = stats_count - live_count

print(f"stats_row_count={stats_count}")
print(f"aggregate_count={aggregate_count}")
print(f"live_query_count={live_count}")
print(f"stats_minus_live={delta}")

if aggregate_count is not None:
    print(
        "aggregate_matches_live="
        f"{aggregate_count == live_count}"
    )

print()
print("===== R2-02B RESULT =====")

hard_failure = any(
    [
        live_count == 0,
        duplicate_id_count > 0,
        missing_id_count > 0,
        missing_doc_id_count > 0,
        len(old_ids) > 0,
    ]
)

if hard_failure:
    print("result=FAIL")
    sys.exit(10)

if stats_count != live_count:
    print(
        "result=PASS_WITH_WARNING_"
        "STATS_AND_LIVE_COUNT_DIFFER"
    )
    sys.exit(0)

print("result=PASS")
sys.exit(0)
