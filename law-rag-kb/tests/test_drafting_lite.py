from __future__ import annotations

from pathlib import Path
import json
import zipfile

from lxml import etree

from app.drafting_lite import service as drafting_service
from app.drafting_lite import (
    material_agent,
    party_extraction,
    research_agent,
    renderer,
)
from app.template_engine import compile_template, load_schema, render_template


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = ROOT / "law-rag-kb" / "app" / "template_engine" / "schemas"
TEMPLATE_ROOT = ROOT / "要素式模板" / "起诉状"


class InvalidJsonLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        return "stub output"


class UnsupportedLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        return '{"cause_code":"unsupported","confidence":1,"evidence":[]}'


def _materials(text: str):
    return [
        {
            "file_name": "材料.pdf",
            "page_texts": [{"page_no": 2, "text": text}],
        }
    ]


def test_keyword_fallback_selects_cause_and_preserves_page_source(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: InvalidJsonLLM())
    service = drafting_service.DraftingLiteService()
    result = material_agent.classify_cause(
        _materials("双方签订借款合同，借款人收到借款后未按期还款，现仍欠本金及利息。"),
        "双方签订借款合同，借款人收到借款后未按期还款，现仍欠本金及利息。",
    )

    assert result["cause_code"] == "private_lending"
    assert result["confidence"] >= 0.55
    assert result["evidence"][0]["file_name"] == "材料.pdf"
    assert result["evidence"][0]["page_no"] == 2


def test_identity_only_material_requires_manual_cause(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: InvalidJsonLLM())
    service = drafting_service.DraftingLiteService()
    result = material_agent.classify_cause(
        _materials("中华人民共和国居民身份证 姓名张某 身份证号码"),
        "中华人民共和国居民身份证 姓名张某 身份证号码",
    )
    assert result["cause_code"] == "unsupported"
    assert result["confidence"] == 0


def test_unsupported_llm_result_never_exposes_false_confidence(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: UnsupportedLLM())
    service = drafting_service.DraftingLiteService()
    result = material_agent.classify_cause(_materials("只有身份材料"), "只有身份材料")
    assert result["cause_code"] == "unsupported"
    assert result["confidence"] == 0


def test_insurance_material_is_not_forced_into_sales_contract(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: InvalidJsonLLM())
    service = drafting_service.DraftingLiteService()
    text = "机动车保险合同、电子保单、车险理赔、交通事故、第三者责任险、不计免赔"
    result = material_agent.classify_cause(_materials(text), text)
    assert result["cause_code"] == "unsupported"
    assert result["confidence"] == 0
    assert "保险" in result["evidence"][0]["reason"]


def test_all_eight_complaint_templates_compile_and_render(tmp_path: Path):
    items = [
        ("private_lending_complaint.v1.json", "要素式民间借贷纠纷起诉状.docx"),
        ("sales_contract_complaint.v1.json", "要素式买卖合同纠纷起诉状.docx"),
        ("labor_dispute_complaint.v1.json", "要素式劳动争议起诉状.docx"),
        ("divorce_complaint.v1.json", "要素式离婚纠纷起诉状.docx"),
        ("traffic_accident_complaint.v1.json", "要素式机动车交通事故责任纠纷起诉状.docx"),
        ("work_injury_complaint.v1.json", "要素式工伤保险资格或者待遇认定起诉状.docx"),
        ("house_sale_complaint.v1.json", "要素式房屋买卖合同纠纷起诉状.docx"),
        ("house_lease_complaint.v1.json", "要素式房屋租赁合同纠纷起诉状.docx"),
    ]
    for schema_name, template_name in items:
        schema = load_schema(SCHEMA_ROOT / schema_name)
        normalized = tmp_path / f"normalized-{template_name}"
        output = tmp_path / f"output-{template_name}"
        compile_report = compile_template(TEMPLATE_ROOT / template_name, normalized, schema)
        assert compile_report["unresolved_fields"] == []
        values = {
            field.field_id: (
                [{"name": "上传材料", "proof_purpose": "证明案件事实"}]
                if field.value_type == "list"
                else f"【待补充：{field.label}】"
            )
            for field in schema.fields
        }
        render_template(normalized, output, schema, values)
        with zipfile.ZipFile(output) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
        visible = "".join(
            root.xpath(
                "//w:t/text()",
                namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"},
            )
        )
        assert "【待补充：" in visible
        assert "AI 自动生成，请核对材料与内容后使用" not in visible


def test_all_party_bindings_avoid_litigation_agent_rows(tmp_path: Path):
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    for cause, config in drafting_service.CAUSES.items():
        schema = load_schema(SCHEMA_ROOT / config["schema"])
        normalized = tmp_path / f"{cause}-party-bindings.docx"
        compile_template(ROOT / "要素式模板" / config["template"], normalized, schema)
        with zipfile.ZipFile(normalized) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
        controls = root.xpath(
            "//w:sdt[starts-with(w:sdtPr/w:tag/@w:val, 'ld.field:party.')]",
            namespaces=namespace,
        )
        for control in controls:
            field_id = control.xpath(
                "string(w:sdtPr/w:tag/@w:val)", namespaces=namespace
            ).removeprefix("ld.field:")
            row_text = "".join(
                control.xpath("ancestor::w:tr[1]//w:t/text()", namespaces=namespace)
            )
            assert "委托诉讼代理人" not in row_text, (cause, field_id)


def test_traffic_defendant_name_phone_and_id_type_render_in_party_row(
    tmp_path: Path,
):
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    schema = load_schema(SCHEMA_ROOT / "traffic_accident_complaint.v1.json")
    normalized = tmp_path / "traffic-binding-normalized.docx"
    output = tmp_path / "traffic-binding-output.docx"
    compile_template(
        TEMPLATE_ROOT / "要素式机动车交通事故责任纠纷起诉状.docx",
        normalized,
        schema,
    )
    values = {
        field.field_id: (
            [{"name": "事故认定书", "proof_purpose": "证明事故责任"}]
            if field.value_type == "list"
            else f"【待补充：{field.label}】"
        )
        for field in schema.fields
    }
    values.update({
        "party.defendant.name": "韩宝龙",
        "party.defendant.phone": "16593210793",
        "party.defendant.id_type": "身份证",
        "party.defendant.id_number": "320721197903011816",
    })
    render_template(normalized, output, schema, values)
    with zipfile.ZipFile(output) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    rows = root.xpath("//w:tr", namespaces=namespace)
    agent_row = next(
        row for row in rows
        if "委托诉讼代理人" in "".join(
            row.xpath(".//w:t/text()", namespaces=namespace)
        )
        and "被告" not in "".join(row.xpath(".//w:t/text()", namespaces=namespace))
    )
    defendant_row = next(
        row for row in rows
        if "被告" in "".join(row.xpath(".//w:t/text()", namespaces=namespace))
        and "自然人" in "".join(row.xpath(".//w:t/text()", namespaces=namespace))
    )
    agent_text = "".join(agent_row.xpath(".//w:t/text()", namespaces=namespace))
    defendant_text = "".join(
        defendant_row.xpath(".//w:t/text()", namespaces=namespace)
    )
    assert "韩宝龙" not in agent_text
    assert "16593210793" not in agent_text
    assert "姓名：韩宝龙" in defendant_text
    assert "联系电话：16593210793" in defendant_text
    assert "证件类型：身份证" in defendant_text


def test_defendant_natural_person_bindings_do_not_target_agent_row(tmp_path: Path):
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    for schema_name, template_name in (
        ("private_lending_complaint.v1.json", "要素式民间借贷纠纷起诉状.docx"),
        ("sales_contract_complaint.v1.json", "要素式买卖合同纠纷起诉状.docx"),
    ):
        schema = load_schema(SCHEMA_ROOT / schema_name)
        normalized = tmp_path / f"binding-{template_name}"
        compile_template(TEMPLATE_ROOT / template_name, normalized, schema)
        with zipfile.ZipFile(normalized) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
        for field_id in ("party.defendant.name", "party.defendant.phone"):
            controls = root.xpath(
                f'//w:sdt[w:sdtPr/w:tag/@w:val="ld.field:{field_id}"]',
                namespaces=namespace,
            )
            assert len(controls) == 1
            row_text = "".join(
                controls[0].xpath("ancestor::w:tr[1]//w:t/text()", namespaces=namespace)
            )
            assert "被告" in row_text
            assert "委托诉讼代理人" not in row_text


def test_sales_identity_and_fact_values_render_in_correct_cells(tmp_path: Path):
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    schema = load_schema(SCHEMA_ROOT / "sales_contract_complaint.v1.json")
    normalized = tmp_path / "sales-normalized.docx"
    output = tmp_path / "sales-output.docx"
    compile_template(TEMPLATE_ROOT / "要素式买卖合同纠纷起诉状.docx", normalized, schema)
    values = {
        "party.plaintiff.name": "张三",
        "party.plaintiff.gender": "男",
        "party.plaintiff.birth_date": "1980-01-02",
        "party.plaintiff.id_type": "居民身份证",
        "party.plaintiff.id_number": "320000198001020011",
        "party.defendant.organization_name": "测试公司",
        "party.defendant.organization_address": "测试公司住所",
        "document.claims": "请求支付价款。",
        "document.facts_and_reasons": "双方签订买卖合同。",
        "document.legal_basis": "【未检索到可核验法条】",
        "document.evidence_list": [{"name": "合同", "proof_purpose": "证明合同关系"}],
        "sales.performance.summary": "正确落入右侧内容单元格",
    }
    render_template(normalized, output, schema, values)
    with zipfile.ZipFile(output) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))

    visible = "".join(root.xpath("//w:t/text()", namespaces=namespace))
    assert "出生日期：1980年1月2日" in visible
    assert "1980年1月2日年" not in visible
    birth_control = root.xpath(
        '//w:sdt[w:sdtPr/w:tag/@w:val="ld.field:party.plaintiff.birth_date"]',
        namespaces=namespace,
    )[0]
    birth_line = "".join(
        birth_control.xpath("ancestor::w:p[1]//w:t/text()", namespaces=namespace)
    )
    assert birth_line == "出生日期：1980年1月2日"
    assert "证件号码：320000198001020011" in visible
    assert "男☑" in visible and "女□" in visible

    rows = root.xpath("//w:tr", namespaces=namespace)
    natural_defendant_row = next(
        row for row in rows
        if "被告" in "".join(row.xpath(".//w:t/text()", namespaces=namespace))
        and "自然人" in "".join(row.xpath(".//w:t/text()", namespaces=namespace))
    )
    assert "测试公司住所" not in "".join(
        natural_defendant_row.xpath(".//w:t/text()", namespaces=namespace)
    )
    organization_row = next(
        row for row in rows
        if "被告" in "".join(row.xpath(".//w:t/text()", namespaces=namespace))
        and "法人、非法人组织" in "".join(row.xpath(".//w:t/text()", namespaces=namespace))
    )
    assert "测试公司" in "".join(
        organization_row.xpath(".//w:t/text()", namespaces=namespace)
    )

    performance_row = next(
        row for row in rows
        if "8. 价款支付及标的物交" in "".join(
            row.xpath(".//w:t/text()", namespaces=namespace)
        )
    )
    cells = performance_row.xpath("./w:tc", namespaces=namespace)
    assert "正确落入右侧内容单元格" not in "".join(
        cells[0].xpath(".//w:t/text()", namespaces=namespace)
    )
    assert "正确落入右侧内容单元格" in "".join(
        cells[1].xpath(".//w:t/text()", namespaces=namespace)
    )
    facts_control = root.xpath(
        '//w:sdt[w:sdtPr/w:tag/@w:val="ld.field:document.facts_and_reasons"]',
        namespaces=namespace,
    )[0]
    facts_row_text = "".join(
        facts_control.xpath("ancestor::w:tr[1]//w:t/text()", namespaces=namespace)
    )
    assert "可完整表述纠纷涉及的事实与理由" in facts_row_text
    assert "双方签订买卖合同。" in facts_row_text


def test_party_type_suppresses_irrelevant_identity_block():
    service = drafting_service.DraftingLiteService()
    values = {
        "party.plaintiff.entity_type": "natural_person",
        "party.defendant.entity_type": "organization",
    }
    assert not renderer.field_applies_to_party_type(
        "party.plaintiff.unified_social_credit_code", values
    )
    assert not renderer.field_applies_to_party_type(
        "party.defendant.id_number", values
    )
    assert renderer.field_applies_to_party_type(
        "party.plaintiff.id_number", values
    )
    assert renderer.field_applies_to_party_type(
        "party.defendant.unified_social_credit_code", values
    )


def test_knowledge_snapshot_parses_without_upload_parser(tmp_path: Path):
    service = drafting_service.DraftingLiteService()
    service.jobs_root = tmp_path
    service.store.update = lambda *args, **kwargs: {}
    input_root = tmp_path / "job-1" / "input"
    input_root.mkdir(parents=True)
    snapshot = {
        "document_id": 290,
        "title": "陶士娇卷宗",
        "file_name": "陶士娇卷宗.pdf",
        "chunks": [
            {
                "chunk_id": "290:m:0002",
                "chunk_idx": 2,
                "text": "原告陶士娇，被告薛红娟，借款6000元。",
                "page_no": 1,
                "source_id": 88,
                "source_title": "民事起诉状",
                "source_file_name": "起诉状.pdf",
                "content_hash": "chunk-hash",
            }
        ],
    }
    (input_root / "kb-290.json").write_text(
        json.dumps(snapshot, ensure_ascii=False),
        encoding="utf-8",
    )

    materials = material_agent.parse_materials(
        "job-1",
        [{
            "source_kind": "knowledge",
            "snapshot_name": "kb-290.json",
            "name": "陶士娇卷宗",
            "sha256": "snapshot-hash",
        }],
        [],
        service.jobs_root,
        service.store,
    )

    assert materials[0]["source_kind"] == "knowledge"
    assert materials[0]["document_id"] == 290
    assert materials[0]["page_texts"][0]["chunk_id"] == "290:m:0002"
    assert materials[0]["page_texts"][0]["page_no"] == 1


class BatchedExtractionLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        return json.dumps({
            "parties": [
                {
                    "role": "plaintiff",
                    "entity_type": "natural_person",
                    "name": "陶士娇",
                    "id_number": "320722199002033060",
                    "sources": {
                        "role": [1],
                        "entity_type": [1],
                        "name": [1],
                        "id_number": [1],
                    },
                },
                {
                    "role": "defendant",
                    "entity_type": "natural_person",
                    "name": "薛红娟",
                    "id_number": "320723198809272021",
                    "sources": {
                        "role": [2],
                        "entity_type": [2],
                        "name": [2],
                        "id_number": [2],
                    },
                },
            ],
        }, ensure_ascii=False)


def test_batched_extraction_keeps_tail_chunks_and_chunk_provenance(monkeypatch):
    monkeypatch.setattr(party_extraction, "get_llm", lambda: BatchedExtractionLLM())
    service = drafting_service.DraftingLiteService()
    materials = [{
        "source_kind": "knowledge",
        "document_id": 290,
        "file_name": "陶士娇卷宗.pdf",
        "content_hash": "doc-hash",
        "page_texts": [
            {
                "page_no": 1,
                "chunk_id": "290:m:0001",
                "chunk_idx": 1,
                "document_id": 290,
                "text": "原告信息" + "甲" * 19_996,
                "content_hash": "a",
            },
            {
                "page_no": 18,
                "chunk_id": "290:m:0024",
                "chunk_idx": 24,
                "document_id": 290,
                "text": "尾部被告信息",
                "content_hash": "b",
            },
        ],
    }]
    result = party_extraction.extract_parties(materials)
    parties = {item["role"]: item for item in result["parties"]}

    assert parties["plaintiff"]["name"] == "陶士娇"
    assert parties["defendant"]["name"] == "薛红娟"
    assert parties["defendant"]["field_provenance"]["name"][0]["chunk_id"] == "290:m:0024"
    assert parties["defendant"]["field_provenance"]["name"][0]["page_no"] == 18


class ConflictingExtractionLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        value = "6000" if "第一份本金" in prompt else "6500"
        return json.dumps({
            "values": {"claims.principal.amount": value},
            "sources": {"claims.principal.amount": [1]},
        }, ensure_ascii=False)


def test_conflicting_candidates_are_not_silently_overwritten(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: ConflictingExtractionLLM())
    service = drafting_service.DraftingLiteService()
    warnings: list[str] = []
    materials = [{
        "file_name": "材料.pdf",
        "content_hash": "doc-hash",
        "page_texts": [
            {"page_no": 1, "text": "还欠第一份本金" + "甲" * 19_993},
            {"page_no": 2, "text": "还欠第二份本金"},
        ],
    }]
    values, provenance = material_agent.extract_elements(
        "private_lending",
        materials,
        warnings,
    )

    assert "claims.principal.amount" in values
    assert values["claims.principal.amount"] is not None
    assert any("claims.principal.amount" in warning for warning in warnings)


def test_deterministic_fallback_extracts_labeled_identity_and_remaining_principal(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: InvalidJsonLLM())
    service = drafting_service.DraftingLiteService()
    text = """委托方（原告）：陶士娇
身份证号码：320722199002033060
电话：15996131080
地址：江苏省连云港市海州区凤祥名居3号楼1单元1403
对方基本信息（被告）：薛红娟
身份证号码：320723198809272021
电话：18861377169
地址：江苏省连云港市海州区板浦镇东辛村东辛街22号
2025年10月3日对方跟我借6000元，微信转账给对方，节后给我。
2025年12月11日还了1000元，2026年5月16日还了500元，至今还欠4500元。"""
    materials = [{
        "source_kind": "knowledge",
        "document_id": 290,
        "file_name": "陶士娇卷宗.pdf",
        "page_texts": [{
            "page_no": 1,
            "chunk_id": "290:m:0002",
            "document_id": 290,
            "text": text,
            "content_hash": "a",
        }],
    }]

    party_result = party_extraction.extract_parties(materials)
    parties = {item["role"]: item for item in party_result["parties"]}
    values, provenance = material_agent.extract_case_elements(
        "private_lending",
        materials,
        [],
    )

    assert parties["plaintiff"]["name"] == "陶士娇"
    assert parties["plaintiff"]["id_number"] == "320722199002033060"
    assert parties["defendant"]["name"] == "薛红娟"
    assert parties["defendant"]["phone"] == "18861377169"
    assert values["claims.principal.amount"] == "4500元"
    assert values["loan.principal.agreed"] == "6000元"
    assert values["loan.delivery.items"] == "2025-10-03 微信转账6000元"
    assert parties["plaintiff"]["field_provenance"]["name"][0]["chunk_id"] == "290:m:0002"


def test_private_lending_delivery_items_replace_template_date_placeholders(tmp_path: Path):
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    schema = load_schema(SCHEMA_ROOT / "private_lending_complaint.v1.json")
    normalized = tmp_path / "private-normalized.docx"
    output = tmp_path / "private-output.docx"
    compile_template(TEMPLATE_ROOT / "要素式民间借贷纠纷起诉状.docx", normalized, schema)
    values = {
        field.field_id: (
            [{"name": "材料", "proof_purpose": "证明事实"}]
            if field.value_type == "list"
            else f"【待补充：{field.label}】"
        )
        for field in schema.fields
    }
    values["loan.delivery.items"] = "2025-10-03 微信转账6000元"
    render_template(normalized, output, schema, values)

    with zipfile.ZipFile(output) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    row = next(
        item for item in root.xpath("//w:tr", namespaces=namespace)
        if "6. 借款提供时间" in "".join(
            item.xpath(".//w:t/text()", namespaces=namespace)
        )
    )
    cells = row.xpath("./w:tc", namespaces=namespace)
    detail = "".join(cells[1].xpath(".//w:t/text()", namespaces=namespace))
    assert detail == "2025-10-03 微信转账6000元"
    assert "年" not in detail


def test_authority_relevance_rejects_tax_law_and_accepts_borrowing_rule():
    service = drafting_service.DraftingLiteService()

    class Hit:
        def __init__(self, title: str, text: str):
            self.doc_title = title
            self.text = text

    assert not research_agent.authority_relevant(
        "private_lending",
        Hit("中华人民共和国企业所得税法实施条例", "企业贷款利息支出可以扣除。"),
    )
    assert research_agent.authority_relevant(
        "private_lending",
        Hit("中华人民共和国民法典", "借款人应当按照约定期限返还借款。"),
    )


def test_delivery_item_formats_merge_to_one_semantic_value():
    expected = "2025-10-03 微信转账6000元"
    assert material_agent._normalize_extracted_value(
        "loan.delivery.items",
        [{"date": "2025-10-03", "method": "微信转账", "amount": 6000}],
    ) == expected
    assert material_agent._normalize_extracted_value(
        "loan.delivery.items",
        "2025年10月3日通过微信转账交付6000元",
    ) == expected
