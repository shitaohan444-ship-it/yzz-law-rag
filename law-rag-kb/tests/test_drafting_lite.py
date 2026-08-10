from __future__ import annotations

from pathlib import Path
import json
import zipfile

from lxml import etree
import pytest

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


class ExplodingCauseLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        raise AssertionError("明确案由不应再调用LLM分类")


class WrongSalesCauseLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        return '{"cause_code":"sales_contract","confidence":0.99,"evidence":[]}'


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
    assert len(result["candidates"]) == 3


def test_unreliable_cause_returns_top_three_normalized_candidates(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: InvalidJsonLLM())
    text = "材料提及借款、买卖合同和劳动合同，但没有说明本案具体争议关系。"

    result = material_agent.classify_cause(_materials(text), text)

    assert result["cause_code"] == "unsupported"
    assert [item["cause_code"] for item in result["candidates"]] == [
        "private_lending",
        "sales_contract",
        "labor_dispute",
    ]
    assert sum(item["confidence"] for item in result["candidates"]) == pytest.approx(
        1.0,
        abs=0.000002,
    )
    assert all(item["label"] for item in result["candidates"])


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


def test_all_ten_complaint_templates_compile_and_render(tmp_path: Path):
    assert len(drafting_service.CAUSES) == 10
    for cause, config in drafting_service.CAUSES.items():
        schema = load_schema(SCHEMA_ROOT / config["schema"])
        template_name = Path(config["template"]).name
        normalized = tmp_path / f"normalized-{template_name}"
        output = tmp_path / f"output-{template_name}"
        compile_report = compile_template(TEMPLATE_ROOT / template_name, normalized, schema)
        assert compile_report["unresolved_fields"] == [], cause
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


def test_intellectual_property_keyword_fallback_distinguishes_causes(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: InvalidJsonLLM())
    trademark_text = (
        "原告提交商标注册证，注册商标核定商品为服装。"
        "被告销售侵权商品并使用近似商标和侵权标识。"
    )
    patent_text = (
        "涉案权利为发明专利，专利号明确。原告依据权利要求书，"
        "将被诉侵权产品逐项进行技术特征和等同特征比对。"
    )

    trademark = material_agent.classify_cause(
        _materials(trademark_text), trademark_text
    )
    patent = material_agent.classify_cause(_materials(patent_text), patent_text)

    assert trademark["cause_code"] == "trademark_infringement"
    assert patent["cause_code"] == "invention_patent_infringement"


def test_strong_cause_keywords_reject_contradictory_llm_result(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: WrongSalesCauseLLM())
    text = (
        "原告提交商标注册证和注册商标权利材料，核定商品为服装。"
        "被告使用侵权标识和近似商标，并销售侵权商品。"
    )

    result = material_agent.classify_cause(_materials(text), text)

    assert result["cause_code"] == "trademark_infringement"
    assert result["confidence"] >= 0.9


def test_strong_cause_keywords_reject_unsupported_llm_result(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: UnsupportedLLM())
    text = (
        "涉案发明专利具有明确专利号和权利要求。被诉侵权产品的技术特征"
        "依照全面覆盖原则及等同特征进行逐项比对，并存在无效宣告程序。"
    )

    result = material_agent.classify_cause(_materials(text), text)

    assert result["cause_code"] == "invention_patent_infringement"
    assert result["confidence"] >= 0.9


def test_explicit_cause_in_markdown_overrides_other_case_keywords(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: ExplodingCauseLLM())
    chunk_text = (
        "双方曾签订买卖合同，材料另有订单、送货单、对账单、发票、"
        "货款支付及验收记录。"
    )
    materials = [
        {
            "file_name": "案件材料.md",
            "title": "案件材料",
            "body_markdown": (
                "# 起诉案件信息\n\n"
                "## 案由\n\n"
                "**侵害商标权纠纷**\n\n"
                "下列合同仅用于证明被诉商品的采购和销售过程。"
            ),
            "page_texts": [{"page_no": None, "text": chunk_text, "chunk_id": "chunk-1"}],
        }
    ]

    result = material_agent.classify_cause(materials, chunk_text)

    assert result["cause_code"] == "trademark_infringement"
    assert result["confidence"] == 1.0
    assert result["resolution"] == "explicit_cause"
    assert "Markdown明确记载案由" in result["evidence"][0]["reason"]


def test_explicit_cause_in_later_chunk_overrides_wrong_background(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: ExplodingCauseLLM())
    chunks = [
        {
            "page_no": 1,
            "chunk_id": "trademark-background",
            "text": (
                "附件包括商标注册证、注册商标、核定商品、近似商标、"
                "侵权标识、销售侵权商品及商标许可材料。"
            ),
        },
        {
            "page_no": 9,
            "chunk_id": "explicit-patent-cause",
            "text": "案件基本信息\n案由：侵害发明专利权纠纷",
        },
    ]
    materials = [{"file_name": "知识库材料", "page_texts": chunks}]
    combined = "\n\n".join(chunk["text"] for chunk in chunks)

    result = material_agent.classify_cause(materials, combined)

    assert result["cause_code"] == "invention_patent_infringement"
    assert result["confidence"] == 1.0
    assert result["evidence"][0]["chunk_id"] == "explicit-patent-cause"


def test_explicit_house_sale_cause_beats_nested_sales_contract_name(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: ExplodingCauseLLM())
    text = "案由：房屋买卖合同纠纷"

    result = material_agent.classify_cause(_materials(text), text)

    assert result["cause_code"] == "house_sale"
    assert result["confidence"] == 1.0


def test_explicit_cause_name_split_between_chunks_is_still_recognized(monkeypatch):
    monkeypatch.setattr(material_agent, "get_llm", lambda: ExplodingCauseLLM())
    chunks = [
        {"page_no": 1, "chunk_id": "cause-a", "text": "案由：侵害发明专利"},
        {"page_no": 1, "chunk_id": "cause-b", "text": "权纠纷\n其他案件信息"},
    ]
    materials = [{"file_name": "切片材料.md", "page_texts": chunks}]
    combined = "\n".join(chunk["text"] for chunk in chunks)

    result = material_agent.classify_cause(materials, combined)

    assert result["cause_code"] == "invention_patent_infringement"
    assert result["confidence"] == 0.99


def test_generic_repeat_renderer_fills_all_patent_attachments(tmp_path: Path):
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    schema = load_schema(
        SCHEMA_ROOT / "invention_patent_infringement_complaint.v1.json"
    )
    normalized = tmp_path / "patent-normalized.docx"
    output = tmp_path / "patent-output.docx"
    compile_template(
        TEMPLATE_ROOT / "要素式侵害发明专利权纠纷起诉状.docx",
        normalized,
        schema,
    )
    values = {
        field.field_id: (
            [{"value": f"【待补充：{field.label}】"}]
            if field.value_type == "list"
            else f"【待补充：{field.label}】"
        )
        for field in schema.fields
        if field.required_policy == "required"
    }
    values.update(
        {
            "party.plaintiff.name": "张三",
            "patent.name": "一种测试装置",
            "patent.number": "ZL202310000001.2",
            "patent.accused_product": "测试型号A产品",
            "patent.validity_statistics_period": "2026年7月29日",
            "patent.validity_statistics_date": "2026-07-29",
            "patent.civil_statistics_period": "2026年7月29日",
            "patent.civil_statistics_date": "2026-07-29",
            "document.evidence_list": [
                {
                    "number": "1-1",
                    "page_no": "1-3",
                    "evidence_name": "发明专利证书",
                    "source": "原告提交",
                    "proof_purpose": "证明专利权有效",
                }
            ],
            "patent.independent_claim_features": [
                {
                    "sequence": str(index),
                    "patent_feature": f"专利特征{index}",
                    "accused_feature": f"产品特征{index}",
                    "means_comparison": "手段相同",
                    "function_comparison": "功能相同",
                    "effect_comparison": "效果相同",
                    "obviousness_explanation": "无需创造性劳动即可联想到",
                    "result": "等同",
                }
                for index in range(1, 4)
            ],
            "patent.dependent_claim_features": [
                {
                    "sequence": "1",
                    "patent_feature": "从属特征1",
                    "accused_feature": "产品从属特征1",
                    "result": "相同",
                }
            ],
            "patent.validity_proceedings": [
                {
                    "sequence": "1",
                    "requester": "甲公司",
                    "request_and_reasons": "请求宣告权利要求1无效",
                    "decision_and_date": "第100号决定，2026年1月1日",
                    "decision_result": "维持专利权有效",
                    "administrative_action": "否",
                },
                {
                    "sequence": "2",
                    "requester": "乙公司",
                    "request_and_reasons": "请求宣告权利要求2无效",
                    "decision_result": "审理中",
                },
            ],
            "patent.related_civil_cases": [
                {
                    "sequence": "1",
                    "cause": "侵害发明专利权纠纷",
                    "first_instance_court_case_no": "测试法院（2026）测01号",
                    "claims": "停止侵权并赔偿损失",
                    "summary": "涉及相同专利",
                },
                {
                    "sequence": "2",
                    "cause": "专利权权属纠纷",
                    "first_instance_court_case_no": "测试法院（2026）测02号",
                    "summary": "涉及相同当事人",
                },
            ],
        }
    )

    report = render_template(normalized, output, schema, values)
    with zipfile.ZipFile(output) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    visible = "".join(root.xpath("//w:t/text()", namespaces=namespace))

    assert report["repeat_rows_populated"] == {
        "patent_evidence_items": 0,
        "independent_claim_feature_items": 3,
        "dependent_claim_feature_items": 1,
        "patent_validity_proceeding_items": 2,
        "patent_related_civil_case_items": 2,
    }
    for expected in (
        "专利特征3",
        "从属特征1",
        "甲公司",
        "乙公司",
        "（2026）测01号",
        "（2026）测02号",
        "一种测试装置",
        "测试型号A产品",
    ):
        assert expected in visible
    assert "发明专利证书" not in visible
    assert "专利名称：xxx" not in visible
    assert "侵害xx专利权纠纷" not in visible


def test_public_party_records_render_multiple_parties_and_third_party(
    tmp_path: Path,
):
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    schema = load_schema(
        SCHEMA_ROOT / "trademark_infringement_complaint.v1.json"
    )
    normalized = tmp_path / "trademark-parties-normalized.docx"
    output = tmp_path / "trademark-parties-output.docx"
    compile_template(
        TEMPLATE_ROOT / "要素式侵害商标权纠纷起诉状.docx",
        normalized,
        schema,
    )
    values = {
        field.field_id: (
            [{"name": "商标注册证", "proof_purpose": "证明商标权"}]
            if field.value_type == "list"
            else f"【待补充：{field.label}】"
        )
        for field in schema.fields
        if field.required_policy == "required"
    }
    values.update(
        {
            "party.plaintiff.name": "张三",
            "party.plaintiff.entity_type": "natural_person",
            "party.defendant.organization_name": "被告科技有限公司",
            "party.defendant.entity_type": "organization",
            "_party_records": {
                "plaintiff": [
                    {"entity_type": "natural_person", "name": "张三", "phone": "13800000001"},
                    {"entity_type": "natural_person", "name": "李四", "phone": "13800000002"},
                ],
                "defendant": [
                    {
                        "entity_type": "organization",
                        "organization_name": "被告科技有限公司",
                        "organization_phone": "01012345678",
                    }
                ],
                "third_party": [
                    {"entity_type": "natural_person", "name": "王五", "phone": "13800000003"}
                ],
            },
        }
    )

    report = render_template(normalized, output, schema, values)
    with zipfile.ZipFile(output) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    rows = root.xpath("//w:tr", namespaces=namespace)
    plaintiff_rows = [
        "".join(row.xpath(".//w:t/text()", namespaces=namespace))
        for row in rows
        if "原告（自然人）" in "".join(
            row.xpath(".//w:t/text()", namespaces=namespace)
        )
    ]
    visible = "".join(root.xpath("//w:t/text()", namespaces=namespace))

    assert len(plaintiff_rows) == 2
    assert any("张三" in row for row in plaintiff_rows)
    assert any("李四" in row for row in plaintiff_rows)
    assert "被告科技有限公司" in visible
    assert "王五" in visible
    assert report["party_rows_populated"] == {
        "plaintiff.natural_person": 2,
        "defendant.organization": 1,
        "third_party.natural_person": 1,
    }


def test_trademark_compiler_removes_attachment_page_break_noise(tmp_path: Path):
    schema = load_schema(
        SCHEMA_ROOT / "trademark_infringement_complaint.v1.json"
    )
    report = compile_template(
        TEMPLATE_ROOT / "要素式侵害商标权纠纷起诉状.docx",
        tmp_path / "trademark-normalized.docx",
        schema,
    )

    assert report["removed_explicit_page_breaks"] == 1


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
        "body_markdown": "## 案由\n\n民间借贷纠纷",
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
    assert materials[0]["body_markdown"] == "## 案由\n\n民间借贷纠纷"
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


class PatentListExtractionLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        if "第一组特征" in prompt:
            feature = {
                "sequence": "1",
                "patent_feature": "第一专利特征",
                "accused_feature": "第一产品特征",
                "result": "相同",
            }
        else:
            feature = {
                "sequence": "2",
                "patent_feature": "第二专利特征",
                "accused_feature": "第二产品特征",
                "result": "等同",
            }
        source_ref = 1 if "第一组特征" in prompt else 2
        return json.dumps(
            {
                "values": {"patent.independent_claim_features": [feature]},
                "sources": {"patent.independent_claim_features": [source_ref]},
            },
            ensure_ascii=False,
        )


def test_structured_lists_merge_across_markdown_chunk_batches(monkeypatch):
    monkeypatch.setattr(
        material_agent, "get_llm", lambda: PatentListExtractionLLM()
    )
    schema = load_schema(
        SCHEMA_ROOT / "invention_patent_infringement_complaint.v1.json"
    )
    materials = [
        {
            "source_kind": "knowledge",
            "document_id": 501,
            "file_name": "专利案件材料.md",
            "page_texts": [
                {
                    "page_no": 10,
                    "chunk_id": "501:m:0010",
                    "text": "第一组特征" + "甲" * 20_500,
                },
                {
                    "page_no": 11,
                    "chunk_id": "501:m:0011",
                    "text": "第二组特征",
                },
            ],
        }
    ]

    values, provenance = material_agent.extract_case_elements(
        "invention_patent_infringement",
        materials,
        [],
        schema,
    )

    assert [
        item["patent_feature"]
        for item in values["patent.independent_claim_features"]
    ] == ["第一专利特征", "第二专利特征"]
    assert [source["page_no"] for source in provenance[
        "patent.independent_claim_features"
    ]] == [10, 11]


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
