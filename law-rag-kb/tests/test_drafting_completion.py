from __future__ import annotations

import json

from app.drafting_lite import drafting_agent
from app.drafting_lite.config import CAUSES, _json_object


SOURCE = {
    "source_type": "material",
    "file_name": "案件材料.pdf",
    "page_no": 1,
    "chunk_id": "chunk-1",
}


class CompleteFieldsLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        assert "凡能由材料或已核验字段填写的都必须填写" in prompt
        return json.dumps(
            {
                "values": {
                    "document.claims": (
                        "1. 判令被告偿还借款本金4500元；"
                        "2. 本案诉讼费用由被告承担。"
                    ),
                    "loan.contract.summary": "双方达成6000元借款合意。",
                    "loan.principal.agreed": "6000.00",
                    "loan.repayment.summary": "被告已偿还1500元。",
                    "loan.default.summary": "被告尚欠本金4500元未还。",
                    "document.facts_and_reasons": "被告借款后仅部分还款，尚欠本金4500元。",
                    "party.plaintiff.name": "不得写入",
                },
                "sources": {
                    "document.claims": [1],
                    "loan.contract.summary": [1],
                    "loan.principal.agreed": [1],
                    "loan.repayment.summary": [1],
                    "loan.default.summary": [1],
                    "document.facts_and_reasons": [1],
                    "party.plaintiff.name": [1],
                },
            },
            ensure_ascii=False,
        )


class InvalidJsonLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        return "not json"


def _materials():
    return [
        {
            "file_name": "案件材料.pdf",
            "page_texts": [
                {
                    "page_no": 1,
                    "chunk_id": "chunk-1",
                    "text": (
                        "被告向原告借款6000元，原告通过微信交付。"
                        "被告已偿还1500元，尚欠4500元未还。"
                    ),
                }
            ],
        }
    ]


def test_public_completion_fills_every_source_supported_schema_field(monkeypatch):
    monkeypatch.setattr(drafting_agent, "get_llm", lambda: CompleteFieldsLLM())
    fields = {
        "claims.principal.amount": "4500元",
        "loan.delivery.method": "微信转账",
    }
    provenance = {field_id: [dict(SOURCE)] for field_id in fields}
    warnings: list[str] = []

    values = drafting_agent.draft(
        "private_lending", fields, provenance, _materials(), [], warnings
    )

    assert values["document.claims"].startswith("1. 判令被告")
    assert "诉讼费" not in values["document.claims"]
    assert values["loan.contract.summary"] == "双方达成6000元借款合意。"
    assert values["loan.principal.agreed"] == "6000元"
    assert values["loan.repayment.summary"] == "被告已偿还1500元。"
    assert values["loan.default.summary"] == "被告尚欠本金4500元未还。"
    assert values["document.facts_and_reasons"].startswith("被告借款后")
    assert "party.plaintiff.name" not in values
    assert provenance["loan.contract.summary"][0]["chunk_id"] == "chunk-1"
    assert any("公共完整性填充已补充6个" in item for item in warnings)


def test_completion_computes_total_and_has_safe_claims_fallback(monkeypatch):
    monkeypatch.setattr(drafting_agent, "get_llm", lambda: InvalidJsonLLM())
    fields = {
        "claims.principal.amount": "4500元",
        "claims.interest.amount": "500元",
        "loan.term": "节后归还",
    }
    provenance = {field_id: [dict(SOURCE)] for field_id in fields}
    warnings: list[str] = []

    values = drafting_agent.draft(
        "private_lending", fields, provenance, _materials(), [], warnings
    )

    assert values["claims.total_amount"] == "5000元"
    assert "4500元" in values["document.claims"]
    assert "节后归还" in values["document.facts_and_reasons"]
    assert provenance["claims.total_amount"][0]["computed"] is True
    assert any("确定性回退" in item for item in warnings)


def test_all_causes_share_schema_driven_completion_catalog():
    for cause in CAUSES:
        schema = drafting_agent._schema_for_cause(cause)
        field_ids = {field.field_id for field in drafting_agent._fillable_fields(schema)}
        assert "document.claims" in field_ids, cause
        assert "document.facts_and_reasons" in field_ids, cause
        assert "document.evidence_list" not in field_ids, cause
        assert "document.legal_basis" not in field_ids, cause
    patent_schema = drafting_agent._schema_for_cause(
        "invention_patent_infringement"
    )
    patent_fields = {
        field.field_id for field in drafting_agent._fillable_fields(patent_schema)
    }
    assert "patent.number" in patent_fields


def test_shared_json_parser_preserves_chinese_quotes_inside_valid_json():
    parsed = _json_object(
        '{"values":{"loan.term":"双方约定“节后归还”"},"sources":{}}'
    )
    assert parsed["values"]["loan.term"] == "双方约定“节后归还”"


def test_shared_json_parser_still_accepts_smart_quoted_json_keys():
    parsed = _json_object('“ignored”\n{“values”:{“loan.term”:“节后归还”}}')
    assert parsed["values"]["loan.term"] == "节后归还"
