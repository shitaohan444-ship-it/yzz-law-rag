from __future__ import annotations

from pathlib import Path
import zipfile

from lxml import etree

from app.template_engine import compile_template, load_schema, render_template


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "law-rag-kb" / "app" / "template_engine" / "schemas" / "private_lending_complaint.v1.json"
SOURCE = ROOT / "要素式模板" / "起诉状" / "要素式民间借贷纠纷起诉状.docx"
TRADEMARK_SCHEMA_PATH = ROOT / "law-rag-kb" / "app" / "template_engine" / "schemas" / "trademark_defense.v1.json"
TRADEMARK_SOURCE = ROOT / "要素式模板" / "答辩状" / "要素式侵害商标权纠纷答辩状.docx"


def test_private_lending_template_all_bindings_resolve(tmp_path: Path):
    schema = load_schema(SCHEMA_PATH)
    normalized = tmp_path / "normalized.docx"
    report = compile_template(SOURCE, normalized, schema)

    assert report["required_bindings_ok"] is True
    assert report["unresolved_fields"] == []
    assert len(report["inserted_fields"]) == len(schema.fields)
    assert set(report["inserted_sections"]) == set(schema.sections)
    assert report["inserted_repeats"] == ["evidence_items"]
    assert report["unresolved_semantic_markers"] == []
    assert report["sha256"] == "b28329f27ba054a57fe3c453a0ba4e29f28dff9405820104824688fe619750ac"
    assert report["removed_page_break_before"] > 0
    assert report["removed_intermediate_sections"] > 0


def test_render_keeps_original_read_only_and_adds_ai_notice(tmp_path: Path):
    schema = load_schema(SCHEMA_PATH)
    before = SOURCE.read_bytes()
    normalized = tmp_path / "normalized.docx"
    output = tmp_path / "draft.docx"
    compile_template(SOURCE, normalized, schema)
    values = {
        field.field_id: ("测试值" if field.value_type != "list" else ["测试项"])
        for field in schema.fields
        if field.required_policy == "required"
    }
    values["loan.delivery.method"] = "银行转账"
    report = render_template(normalized, output, schema, values)

    assert report["empty_required_fields"] == []
    assert SOURCE.read_bytes() == before
    with zipfile.ZipFile(output) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    visible = "".join(root.xpath("//w:t/text()", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}))
    assert "AI 自动生成，请核对材料与内容后使用" not in visible
    assert "测试值" in visible
    assert "现金□" in visible
    assert "转账☑" in visible
    assert report["checkbox_fields"] == ["loan.delivery.method"]
    assert "{pic_qmPath}" not in visible
    assert report["cleared_user_only_placeholders"] == []


def test_trademark_defense_template_has_evidence_and_objection_repeat_markers(tmp_path: Path):
    schema = load_schema(TRADEMARK_SCHEMA_PATH)
    report = compile_template(TRADEMARK_SOURCE, tmp_path / "trademark.docx", schema)

    assert report["required_bindings_ok"] is True
    assert report["unresolved_fields"] == []
    assert len(report["inserted_fields"]) == 17
    assert set(report["inserted_sections"]) == set(schema.sections)
    assert set(report["inserted_repeats"]) == {
        "own_evidence_items",
        "opponent_evidence_items",
    }


def test_trademark_defense_populates_repeat_rows(tmp_path: Path):
    schema = load_schema(TRADEMARK_SCHEMA_PATH)
    normalized = tmp_path / "trademark-normalized.docx"
    output = tmp_path / "trademark-draft.docx"
    compile_template(TRADEMARK_SOURCE, normalized, schema)
    values = {
        field.field_id: "已确认内容"
        for field in schema.fields
        if field.required_policy == "required"
    }
    values["document.evidence_list"] = [
        {
            "number": "1",
            "page_no": "3-5",
            "evidence_name": "合法来源合同",
            "source": "答辩人提交",
            "proof_purpose": "证明合法来源",
        }
    ]
    values["document.opponent_evidence_objections"] = [
        {
            "number": "1-1",
            "evidence_name": "商标注册证",
            "authenticity": "无异议",
            "legality": "无异议",
            "relevance": "有异议",
            "probative_force": "不能证明被诉行为构成侵权",
        }
    ]
    report = render_template(normalized, output, schema, values)

    with zipfile.ZipFile(output) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    visible = "".join(root.xpath("//w:t/text()", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}))
    assert "合法来源合同" in visible
    assert "商标注册证" in visible
    assert "不能证明被诉行为构成侵权" in visible
    assert report["repeat_rows_populated"] == {
        "own_evidence_items": 1,
        "opponent_evidence_items": 1,
    }
