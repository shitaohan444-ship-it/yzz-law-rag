from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile

from lxml import etree

from app.drafting_lite import evidence_directory
from app.drafting_lite.config import CAUSES
from app.template_engine import compile_template, load_schema, render_template


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = ROOT / "law-rag-kb" / "app" / "template_engine" / "schemas"
TEMPLATE_ROOT = ROOT / "要素式模板"
NAMESPACE = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
}


class InvalidJsonLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        return "not-json"


class SemanticEvidenceLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        return """{
          "items": [
            {"name":"借款合同","proof_purpose":"证明双方存在借款合同关系","source_numbers":[1],"fact_field_refs":["loan.contract.summary"]},
            {"name":"微信转账记录","proof_purpose":"证明原告已实际交付借款","source_numbers":[1],"fact_field_refs":[]}
          ]
        }"""


class HallucinatedNumberLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        return """{
          "items": [
            {"name":"借款合同","proof_purpose":"证明被告应偿还999999元","source_numbers":[1],"fact_field_refs":[]}
          ]
        }"""


def _material(text: str, *, name: str = "合并材料.pdf") -> list[dict]:
    return [
        {
            "material_id": 1,
            "file_name": name,
            "content_hash": hashlib.sha256(text.encode()).hexdigest(),
            "page_texts": [
                {
                    "page_no": 1,
                    "chunk_id": "chunk-1",
                    "text": text,
                    "content_hash": hashlib.sha256(text.encode()).hexdigest(),
                }
            ],
        }
    ]


def test_explicit_headings_split_actual_evidence(monkeypatch):
    monkeypatch.setattr(evidence_directory, "get_llm", lambda: InvalidJsonLLM())
    materials = _material(
        "证据一：借款合同\n合同约定借款事项。\n"
        "证据二：微信转账记录\n记录显示发生转账。"
    )

    result = evidence_directory.extract_evidence_directory(
        materials,
        {},
        {},
        "请求返还借款",
        [],
    )

    assert [item.name for item in result.items] == ["借款合同", "微信转账记录"]
    assert all(item.source_refs[0].chunk_id == "chunk-1" for item in result.items)
    assert result.status == "partial"


def test_llm_can_semantically_split_one_material_with_verified_names(monkeypatch):
    monkeypatch.setattr(
        evidence_directory,
        "get_llm",
        lambda: SemanticEvidenceLLM(),
    )
    result = evidence_directory.extract_evidence_directory(
        _material("借款合同\n双方约定借款。\n微信转账记录\n原告向被告转账。"),
        {"loan.contract.summary": "双方签订借款合同"},
        {"loan.contract.summary": [{"file_name": "合并材料.pdf", "page_no": 1}]},
        "请求返还借款",
        [],
    )

    assert result.status == "generated"
    assert [item.name for item in result.items] == ["借款合同", "微信转账记录"]
    assert result.items[0].fact_field_refs == ["loan.contract.summary"]


def test_unsupported_numeric_fact_in_proof_purpose_is_rejected(monkeypatch):
    monkeypatch.setattr(
        evidence_directory,
        "get_llm",
        lambda: HallucinatedNumberLLM(),
    )
    result = evidence_directory.extract_evidence_directory(
        _material("借款合同\n双方签订借款合同。"),
        {},
        {},
        "请求返还借款",
        [],
    )

    assert result.items[0].proof_purpose == evidence_directory.PLACEHOLDER_PURPOSE
    assert "proof_purpose_unsupported" in result.items[0].validation_issues


def test_evidence_template_renderer_removes_real_sample_and_expands(tmp_path: Path):
    template = TEMPLATE_ROOT / "证据目录模板" / "证据目录模板.docx"
    before = hashlib.sha256(template.read_bytes()).hexdigest()
    items = [
        evidence_directory.EvidenceItem(
            evidence_id=f"ev-{index}",
            sequence=index,
            name=f"测试证据{index}",
            proof_purpose=f"证明测试事实{index}",
            source_refs=[
                evidence_directory.EvidenceSourceRef(
                    material_id=1,
                    file_name="测试材料.pdf",
                    page_no=index,
                )
            ],
            extraction_method="test",
        )
        for index in range(1, 8)
    ]
    result = evidence_directory.EvidenceDirectoryResult(
        status="generated",
        items=items,
    )

    output, filename, audit = evidence_directory.render_evidence_directory(
        "job-1",
        "民间借贷纠纷",
        "张三",
        result,
        tmp_path,
        TEMPLATE_ROOT,
    )

    assert filename == "民间借贷纠纷_张三_证据目录.docx"
    assert output.is_file() and audit.is_file()
    assert hashlib.sha256(template.read_bytes()).hexdigest() == before
    with zipfile.ZipFile(output) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    visible = "".join(root.xpath("//w:t/text()", namespaces=NAMESPACE))
    assert "测试证据7" in visible
    assert "双方微信聊天记录" not in visible
    assert "23,241.39元" not in visible
    name_paragraphs = root.xpath(
        "//w:p[contains(string(.), '证据') and not(contains(string(.), '证明目的'))]",
        namespaces=NAMESPACE,
    )
    assert any(
        paragraph.find("w:pPr/w:keepNext", namespaces=NAMESPACE) is not None
        for paragraph in name_paragraphs
    )


def test_all_complaint_schemas_externalize_inline_evidence(tmp_path: Path):
    for cause, config in CAUSES.items():
        schema = load_schema(SCHEMA_ROOT / str(config["schema"]))
        evidence_directory.validate_evidence_directory_schema(schema)
        normalized = tmp_path / f"{cause}-normalized.docx"
        output = tmp_path / f"{cause}-output.docx"
        compile_template(
            TEMPLATE_ROOT / str(config["template"]),
            normalized,
            schema,
        )
        values = {
            field.field_id: (
                [{"name": "UNIQUE_INLINE_EVIDENCE", "proof_purpose": "证明事实"}]
                if field.field_id == "document.evidence_list"
                else (
                    [{"value": f"【待补充：{field.label}】"}]
                    if field.value_type == "list"
                    else f"【待补充：{field.label}】"
                )
            )
            for field in schema.fields
        }
        render_template(normalized, output, schema, values)
        with zipfile.ZipFile(output) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
        visible = "".join(root.xpath("//w:t/text()", namespaces=NAMESPACE))
        assert "UNIQUE_INLINE_EVIDENCE" not in visible, cause
