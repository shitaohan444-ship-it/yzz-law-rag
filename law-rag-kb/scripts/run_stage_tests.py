"""阶段 3-7 集成测试：检索、真实 LLM 生成、引用/日志、批量入库、法条精度与拒答。

用法（在 law-rag-kb 目录）：
    set HF_HUB_OFFLINE=1 && python scripts/run_stage_tests.py     # Windows cmd
    HF_HUB_OFFLINE=1 python scripts/run_stage_tests.py            # bash
退出码 0 = 全过，1 = 有失败。
"""
import importlib.util
import os
import sys
from pathlib import Path

# 让脚本能 import app 包 + 把 cwd 固定到 law-rag-kb（config 的 .env 相对 cwd）
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.milvus_client import get_milvus_client  # noqa: E402
from app.main import app  # noqa: E402

_client_headers: dict[str, str] = {}
if settings.auth_enabled:
    _test_user_id = os.getenv("RAG_TEST_USER_ID", "").strip()
    if not settings.rag_service_token or not _test_user_id:
        raise SystemExit(
            "AUTH_ENABLED=true requires RAG_SERVICE_TOKEN and RAG_TEST_USER_ID"
        )
    _client_headers = {
        "Authorization": f"Bearer {settings.rag_service_token}",
        "X-RAG-User-Id": _test_user_id,
    }

client = TestClient(app, headers=_client_headers)
R: list[tuple[str, bool, str]] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    R.append((name, bool(ok), detail))
    tag = "PASS" if ok else "FAIL"
    line = f"  [{tag}] {name}"
    if detail:
        line += f"  ::  {detail}"
    print(line)


def q_doc_ids() -> list[int]:
    mc = get_milvus_client()
    mc.load_collection(settings.milvus_collection)
    rows = mc.query(
        settings.milvus_collection,
        filter="doc_id >= 0",
        output_fields=["doc_id"],
        limit=16384,
        consistency_level="Strong",
    )
    return sorted(set(r["doc_id"] for r in rows))


def chat_count() -> int:
    with SessionLocal() as db:
        return db.execute(text("SELECT count(*) FROM oa.ai_chat_log")).scalar()


# =================== A. 基础设施 & 数据状态 ===================
print("== A. 基础设施 & 数据 ==")
h = client.get("/health").json()
chk("A1 /health pg/minio/milvus 均 ok", all(h.get(k) == "ok" for k in ("pg", "minio", "milvus")), str(h))

doc_ids = q_doc_ids()
chk("A2 kb_chunks 有数据", len(doc_ids) > 0, f"{len(doc_ids)} distinct doc_ids")
chk("A2b 含批量入库新文档(id>=10)", any(d >= 10 for d in doc_ids), str(doc_ids))

with SessionLocal() as db:
    succ = db.execute(text("SELECT count(*) FROM oa.kb_document WHERE embedding_status='success'")).scalar()
    total = db.execute(text("SELECT count(*) FROM oa.kb_document")).scalar()
chk("A3 存在 success 状态文档", succ > 0, f"success={succ}/{total}")

# =================== B. /search 检索链 ===================
print("\n== B. /search 检索链 ==")
r = client.post("/search", json={"query": "劳动合同试用期", "top_k": 5})
b = r.json()
chk("B1 正常检索 200", r.status_code == 200, str(r.status_code))
chk("B1b 返回数 ≤ top_k", len(b["hits"]) <= 5, f"{len(b['hits'])} hits")
if b["hits"]:
    h0 = b["hits"][0]
    need = {"chunk_id", "doc_id", "doc_title", "source", "chunk_idx", "text", "score"}
    chk("B1c hit 字段完整", need <= set(h0.keys()), str(sorted(h0.keys())))
    scores = [x["score"] for x in b["hits"]]
    chk("B1d score 降序", scores == sorted(scores, reverse=True), str([round(s, 3) for s in scores]))
    chk("B1e score ∈ [0,1]", all(0.0 <= s <= 1.0 for s in scores), str([round(s, 3) for s in scores]))
    titles = {x["doc_title"] for x in b["hits"]}
    chk("B1f 命中劳动合同法", "劳动合同法" in titles, str(titles))

chk("B2a 空 query → 422", client.post("/search", json={"query": ""}).status_code == 422)
chk("B2b top_k=0 → 422", client.post("/search", json={"query": "x", "top_k": 0}).status_code == 422)
chk("B2c top_k=51 → 422", client.post("/search", json={"query": "x", "top_k": 51}).status_code == 422)
chk("B2d top_k=-1 → 422", client.post("/search", json={"query": "x", "top_k": -1}).status_code == 422)
chk("B2e 缺 query → 422", client.post("/search", json={"top_k": 3}).status_code == 422)

target = doc_ids[0]
r = client.post("/search", json={"query": "法律", "doc_ids": [target], "top_k": 5})
chk("B3 doc_ids 过滤仅返回该 doc", all(x["doc_id"] == target for x in r.json()["hits"]),
    f"target={target} got={set(x['doc_id'] for x in r.json()['hits'])}")

r = client.post("/search", json={"query": "法律", "doc_ids": [999999]})
chk("B4 不存在 doc_ids → 空结果", r.json()["total"] == 0, str(r.json()["total"]))

r = client.post("/search", json={"query": "诉讼时效", "top_k": 1})
chk("B5 top_k=1 → 恰好 1 条", len(r.json()["hits"]) == 1, str(len(r.json()["hits"])))

# =================== C. /chat 生成链 ===================
print("\n== C. /chat 生成链 ==")
chat_before = chat_count()
r = client.post("/chat", json={"question": "诉讼时效是几年", "top_k": 3})
b = r.json()
cid = b["chat_log_id"]
chk("C1 /chat 200", r.status_code == 200, str(r.status_code))
if settings.llm_provider == "stub":
    chk("C1b Stub provider 返回模板标记", "Stub" in b["answer"], b["answer"][:30])
else:
    chk("C1b 真实 LLM 非 Stub 答案", "Stub" not in b["answer"] and bool(b["answer"].strip()), b["answer"][:45])
    chk("C1b2 真实 LLM 答案含引用编号", "[1]" in b["answer"], b["answer"][:80])
chk("C1c refs 非空", len(b["refs"]) > 0, f"{len(b['refs'])} refs")
chk("C1d chat_log_id 非空", cid is not None, str(cid))
chk("C1e refs ref_id 从 1 连续", [x["ref_id"] for x in b["refs"]] == list(range(1, len(b["refs"]) + 1)),
    str([x["ref_id"] for x in b["refs"]]))
if b["refs"]:
    chk("C1f ref 字段完整", {"ref_id", "chunk_id", "doc_id", "doc_title", "chunk_idx", "source", "score"} <= set(b["refs"][0]),
        str(sorted(b["refs"][0])))

chk("C2a 空 question → 422", client.post("/chat", json={"question": ""}).status_code == 422)
chk("C2b top_k=21 → 422", client.post("/chat", json={"question": "x", "top_k": 21}).status_code == 422)

# session_id 自动生成（uuid）
r = client.post("/chat", json={"question": "侵权赔偿范围"})
sid = None
with SessionLocal() as db:
    sid = db.execute(text("SELECT session_id FROM oa.ai_chat_log WHERE id=:i"), {"i": r.json()["chat_log_id"]}).scalar()
chk("C3 session_id 自动生成(≥16 字符)", sid is not None and len(sid) >= 16, str(sid))

# session_id 传入生效
r = client.post("/chat", json={"question": "违约金", "session_id": "test-sess-123"})
sid2 = None
with SessionLocal() as db:
    sid2 = db.execute(text("SELECT session_id FROM oa.ai_chat_log WHERE id=:i"), {"i": r.json()["chat_log_id"]}).scalar()
chk("C3b session_id 传入生效", sid2 == "test-sess-123", str(sid2))

# ai_chat_log 字段一致性（查 C1 那条）
with SessionLocal() as db:
    log = db.execute(
        text(
            "SELECT user_type, user_id, question_text, answer_text, "
            "manual_takeover_flag, risk_flag, status, "
            "jsonb_typeof(knowledge_refs::jsonb) AS rt, "
            "CASE WHEN knowledge_refs IS NULL THEN 0 ELSE jsonb_array_length(knowledge_refs::jsonb) END AS rc "
            "FROM oa.ai_chat_log WHERE id=:i"
        ),
        {"i": cid},
    ).mappings().first()
ld = dict(log) if log else {}
chk("C4a user_type 默认 user", ld.get("user_type") == "user", str(ld.get("user_type")))
chk("C4b manual_takeover_flag=False", ld.get("manual_takeover_flag") is False, str(ld.get("manual_takeover_flag")))
chk("C4c risk_flag=False", ld.get("risk_flag") is False, str(ld.get("risk_flag")))
chk("C4d status=active", ld.get("status") == "active", str(ld.get("status")))
chk("C4e knowledge_refs 是 array", ld.get("rt") == "array", str(ld.get("rt")))
chk("C4f knowledge_refs 长度=hits_count", ld.get("rc") == b["hits_count"], f"{ld.get('rc')} vs {b['hits_count']}")
chk("C4g answer_text 落库=响应", ld.get("answer_text") == b["answer"], f"len {len(ld.get('answer_text') or '')} vs {len(b['answer'])}")

chk("C5 ai_chat_log 行数增长", chat_count() > chat_before, f"{chat_before} -> {chat_count()}")

# max_chars 截断：大 top_k + 小上限 → 入 prompt 的片段被截断（hits_count 受限）
r = client.post("/chat", json={"question": "法律", "top_k": 8})
# 默认 chat_max_context_chars=4000，8 片段可能未截断；仅验证 hits_count ≤ top_k
chk("C6 hits_count ≤ top_k", r.json()["hits_count"] <= 8, str(r.json()["hits_count"]))

# 真实 LLM 的精确法条引用与无依据拒答（Stub 环境跳过外部生成质量断言）
if settings.llm_provider != "stub":
    r = client.post(
        "/chat",
        json={"question": "产品缺陷造成他人损害，生产者是否承担责任？", "top_k": 3},
    )
    body = r.json()
    articles = [x.get("article_no") for x in body.get("refs", [])]
    chk("C7 Qwen 法律问答 200", r.status_code == 200, str(r.status_code))
    chk("C7b 精确引用民法典第一千二百零二条", "第一千二百零二条" in articles, str(articles))
    chk("C7c 法律答案含引用且非 Stub", "[1]" in body.get("answer", "") and "Stub" not in body.get("answer", ""), body.get("answer", "")[:80])

    r = client.post(
        "/chat",
        json={"question": "盗窃数额较大的刑事量刑标准是什么？", "top_k": 3},
    )
    body = r.json()
    answer = body.get("answer", "")
    chk("C8 无依据问答 200", r.status_code == 200, str(r.status_code))
    chk("C8b 未收录刑法问题明确拒答", "依据不足" in answer or "无法回答" in answer, answer[:100])

# =================== D. 批量入库幂等 ===================
print("\n== D. 批量入库幂等 ==")
spec = importlib.util.spec_from_file_location("batch_ingest", Path(__file__).resolve().parent / "batch_ingest.py")
bi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bi)

f = bi.ROOT / "法律法规" / "民法典合同编.md"
sub = f.parent
with SessionLocal() as db:
    cnt_before = db.execute(text("SELECT count(*) FROM oa.kb_document")).scalar()

rec = bi._ingest_one(sub, f, bi._get_emp(), force=False)
with SessionLocal() as db:
    cnt_after = db.execute(text("SELECT count(*) FROM oa.kb_document")).scalar()
chk("D1 已入库文件默认 → skipped", rec["status"] == "skipped", f"status={rec['status']} doc_id={rec['doc_id']}")
chk("D2 幂等：kb_document 行数不变", cnt_after == cnt_before, f"{cnt_before} -> {cnt_after}")

rec2 = bi._ingest_one(sub, f, bi._get_emp(), force=True)
chk("D3 --force → success 重跑", rec2["status"] == "success", f"status={rec2['status']} chunks={rec2['chunks']}")
chk("D4 force 后 doc_id 不变（复用）", rec2["doc_id"] == rec["doc_id"], f"{rec['doc_id']} vs {rec2['doc_id']}")

# =================== E. 多文档检索质量 ===================
print("\n== E. 多文档检索质量 ==")
cases = [
    ("劳动合同试用期最长多久", "劳动合同法"),
    ("用人单位违法解除劳动合同赔偿金", "劳动争议判决书"),
    ("民间借贷没有约定利息逾期利息", "民间借贷纠纷判决书"),
    ("民事权利的诉讼时效是几年", "律师实务笔记"),
    ("侵害他人造成人身损害赔偿医疗费护理费", "民法典侵权责任编"),
    ("合同违约金过分高于造成的损失", "民法典合同编"),
]
for q, expect in cases:
    r = client.post("/search", json={"query": q, "top_k": 3})
    titles = [x["doc_title"] for x in r.json()["hits"]]
    chk(f"E 命中《{expect}》", expect in titles, f"q='{q[:14]}' got={titles}")

# =================== 汇总 ===================
print("\n" + "=" * 50)
npass = sum(1 for _, ok, _ in R if ok)
nfail = sum(1 for _, ok, _ in R if not ok)
print(f"汇总：PASS={npass}  FAIL={nfail}  TOTAL={len(R)}")
if nfail:
    print("\n失败用例：")
    for n, ok, d in R:
        if not ok:
            print(f"  ✗ {n}  ::  {d}")
sys.exit(0 if nfail == 0 else 1)
