import json
import os
import sys

from pymilvus import MilvusClient


def env_first(*names, default=None):
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return default


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

print("===== R2-03B MILVUS PRESIGNED URL AUDIT =====")
print(f"collection={collection}")
print()

description = client.describe_collection(
    collection_name=collection
)

fields = [
    str(field.get("name") or field.get("field_name") or "")
    for field in description.get("fields", [])
]

candidate_fields = [
    "id",
    "doc_id",
    "source",
    "chunk_text",
    "meta",
]

output_fields = [
    field
    for field in candidate_fields
    if field in fields
]

print("audited_fields=" + ",".join(output_fields))

rows = client.query(
    collection_name=collection,
    filter="",
    output_fields=output_fields,
    limit=16384,
    consistency_level="Strong",
)

patterns = (
    "x-amz-algorithm",
    "x-amz-credential",
    "x-amz-date",
    "x-amz-expires",
    "x-amz-signature",
    "x-amz-signedheaders",
)

match_records = []

for row in rows:
    matched_fields = []

    for field in output_fields:
        value = row.get(field)

        if isinstance(value, (dict, list)):
            text = json.dumps(
                value,
                ensure_ascii=False,
                default=str,
            )
        else:
            text = "" if value is None else str(value)

        lowered = text.lower()

        if any(pattern in lowered for pattern in patterns):
            matched_fields.append(field)

    if matched_fields:
        match_records.append(
            {
                "id": row.get("id"),
                "doc_id": row.get("doc_id"),
                "fields": matched_fields,
            }
        )

print(f"audited_entity_count={len(rows)}")
print(f"matched_entity_count={len(match_records)}")

if match_records:
    print("match_details=")

    for record in match_records[:100]:
        print(
            json.dumps(
                record,
                ensure_ascii=True,
                default=str,
            )
        )

    if len(match_records) > 100:
        print(
            f"...total={len(match_records)}, "
            "only_first_100_displayed"
        )

    print("result=FAIL")
    sys.exit(10)

print("result=PASS")
sys.exit(0)
