from __future__ import annotations

from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from app.rag.retrieve import SearchHit
from app.workflows.legal_drafting import nodes
from app.workflows.legal_drafting.graph import build_graph


ROOT = Path(__file__).resolve().parents[2]


class _UnavailableLLM:
    def generate(self, _prompt: str) -> str:
        raise nodes.LLMServiceError("offline test")


def test_workflow_interrupts_for_missing_confirmed_fields(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(nodes.settings, "legal_drafting_output_root", str(tmp_path))
    monkeypatch.setattr(nodes, "get_llm", lambda: _UnavailableLLM())
    graph = build_graph(checkpointer=MemorySaver())
    result = graph.invoke(
        {
            "run_id": "1",
            "thread_id": "missing-case",
            "snapshot": {"run": {"allowed_knowledge_document_ids": []}, "parties": [], "evidence": []},
            "schema_path": str(ROOT / "law-rag-kb" / "app" / "template_engine" / "schemas" / "private_lending_complaint.v1.json"),
            "template_source_path": str(ROOT / "要素式模板" / "起诉状" / "要素式民间借贷纠纷起诉状.docx"),
            "material_texts": [],
        },
        config={"configurable": {"thread_id": "missing-case"}},
    )
    assert result["status"] == "waiting_user_input"
    assert "party.plaintiff.name" in {item["field_id"] for item in result["missing_elements"]}


def test_workflow_requires_confirmation_for_multiple_parties(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(nodes.settings, "legal_drafting_output_root", str(tmp_path))
    monkeypatch.setattr(nodes, "get_llm", lambda: _UnavailableLLM())
    graph = build_graph(checkpointer=MemorySaver())
    result = graph.invoke(
        {
            "run_id": "multi-party",
            "thread_id": "multi-party",
            "snapshot": {
                "run": {"allowed_knowledge_document_ids": []},
                "parties": [
                    {"id": "1", "party_role": "plaintiff", "party": {"party_name": "甲"}},
                    {"id": "2", "party_role": "plaintiff", "party": {"party_name": "乙"}},
                    {"id": "3", "party_role": "defendant", "party": {"party_name": "丙"}},
                ],
                "evidence": [],
            },
            "schema_path": str(ROOT / "law-rag-kb" / "app" / "template_engine" / "schemas" / "private_lending_complaint.v1.json"),
            "template_source_path": str(ROOT / "要素式模板" / "起诉状" / "要素式民间借贷纠纷起诉状.docx"),
            "material_texts": [],
        },
        config={"configurable": {"thread_id": "multi-party"}},
    )
    assert result["status"] == "waiting_user_input"
    assert result["conflicts"][0]["field_id"] == "party.structure.confirmation"


def test_workflow_renders_when_sources_and_authorities_are_verified(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(nodes.settings, "legal_drafting_output_root", str(tmp_path))
    monkeypatch.setattr(nodes, "get_llm", lambda: _UnavailableLLM())
    monkeypatch.setattr(nodes, "authorized_doc_ids", lambda *_args, **_kwargs: [10])
    monkeypatch.setattr(
        nodes.retrieve,
        "search",
        lambda *_args, **_kwargs: [
            SearchHit(
                chunk_id="chunk-1",
                doc_id=10,
                doc_title="中华人民共和国民法典",
                source="法律法规",
                chunk_idx=1,
                text="借款人应当按照约定的期限返还借款。",
                score=0.98,
                article_no="第六百七十五条",
            )
        ],
    )
    user_values = {
        "claims.principal.amount": "100000",
        "loan.contract.summary": "双方于2025年1月1日签订借款合同。",
        "loan.principal.agreed": "100000",
        "loan.principal.delivered": "100000",
        "loan.delivery.method": "银行转账",
        "loan.term": "2025年1月1日至2025年12月31日",
        "loan.delivery.items": ["2025年1月2日转账100000元"],
    }
    snapshot = {
        "run": {"allowed_knowledge_document_ids": ["10"]},
        "parties": [
            {"id": "1", "party_role": "plaintiff", "party": {"party_name": "张三", "address": "北京市甲区"}},
            {"id": "2", "party_role": "defendant", "party": {"party_name": "李四", "address": "北京市乙区"}},
        ],
        "user_inputs": [
            {"field_id": key, "value_json": value, "resolution_type": "confirmed", "input_version": 1}
            for key, value in user_values.items()
        ],
        "evidence": [{"id": "5", "evidence_name": "借款合同", "proof_purpose": "证明借贷合意"}],
    }
    graph = build_graph(checkpointer=MemorySaver())
    result = graph.invoke(
        {
            "run_id": "2",
            "thread_id": "complete-case",
            "snapshot": snapshot,
            "schema_path": str(ROOT / "law-rag-kb" / "app" / "template_engine" / "schemas" / "private_lending_complaint.v1.json"),
            "template_source_path": str(ROOT / "要素式模板" / "起诉状" / "要素式民间借贷纠纷起诉状.docx"),
            "material_texts": [],
        },
        config={"configurable": {"thread_id": "complete-case"}},
    )
    assert result["status"] == "pending_lawyer_review"
    assert Path(result["docx_path"]).exists()
    assert result["authority_cards"][0]["content_hash"]
    assert not [issue for issue in result["review_issues"] if issue["severity"] == "critical"]


def test_trademark_defense_renders_with_own_evidence_and_itemized_objections(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(nodes.settings, "legal_drafting_output_root", str(tmp_path))
    monkeypatch.setattr(nodes, "get_llm", lambda: _UnavailableLLM())
    monkeypatch.setattr(nodes, "authorized_doc_ids", lambda *_args, **_kwargs: [20])
    monkeypatch.setattr(
        nodes.retrieve,
        "search",
        lambda *_args, **_kwargs: [
            SearchHit(
                chunk_id="tm-law-1", doc_id=20, doc_title="中华人民共和国商标法",
                source="法律法规", chunk_idx=1, text="注册商标专用权受法律保护。",
                score=0.96, article_no="第五十七条",
            )
        ],
    )
    snapshot = {
        "run": {"allowed_knowledge_document_ids": ["20"], "case_id": "99", "cause_code": "trademark_infringement"},
        "template": {"template_code": "civil_defense.trademark_infringement"},
        "parties": [
            {"id": "2", "party_role": "defendant", "party": {"party_name": "乙公司", "address": "上海市"}},
        ],
        "user_inputs": [
            {"field_id": "defense.overall_response", "value_json": "请求驳回原告诉讼请求。", "resolution_type": "confirmed", "input_version": 1},
            {"field_id": "trademark.infringement", "value_json": "被诉标识与涉案商标不近似。", "resolution_type": "confirmed", "input_version": 1},
            {"field_id": "document.opponent_evidence_objections", "value_json": ["对原告证据1真实性无异议，关联性有异议。"], "resolution_type": "confirmed", "input_version": 1},
        ],
        "evidence": [{"id": "8", "evidence_name": "合法来源合同", "proof_purpose": "证明合法来源"}],
    }
    graph = build_graph(checkpointer=MemorySaver())
    result = graph.invoke(
        {
            "run_id": "trademark",
            "thread_id": "trademark",
            "snapshot": snapshot,
            "schema_path": str(ROOT / "law-rag-kb" / "app" / "template_engine" / "schemas" / "trademark_defense.v1.json"),
            "template_source_path": str(ROOT / "要素式模板" / "答辩状" / "要素式侵害商标权纠纷答辩状.docx"),
            "material_texts": [],
        },
        config={"configurable": {"thread_id": "trademark"}},
    )
    assert result["status"] == "pending_lawyer_review"
    assert Path(result["docx_path"]).exists()
    assert result["resolved_elements"]["document.opponent_evidence_objections"]
    assert not [issue for issue in result["review_issues"] if issue["severity"] == "critical"]
