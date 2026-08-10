from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from app.api import drafting_lite as drafting_lite_api
from app.api.drafting_lite import _public_job, list_causes
from app.drafting_lite import (
    drafting_agent,
    evidence_directory,
    evidence_package,
    material_agent,
    party_extraction,
    renderer,
    research_agent,
)
from app.drafting_lite import service as drafting_service
from app.drafting_lite.config import CAUSES
from app.drafting_lite.service import DraftingLiteService
from app.drafting_lite.store import DraftingLiteStore


class InvalidJsonLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        return "not json"


class RecordingExecutor:
    def __init__(self):
        self.submissions = []

    def submit(self, fn, *args):
        self.submissions.append((fn, args))

    def shutdown(self, **kwargs):
        return None


def _id(base17: str) -> str:
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    checks = "10X98765432"
    return base17 + checks[sum(int(base17[i]) * weights[i] for i in range(17)) % 11]


PLAINTIFF_ID = _id("11010119900101001")
DEFENDANT_ID = _id("32010119851212002")


def _service(tmp_path: Path) -> DraftingLiteService:
    service = DraftingLiteService()
    service.executor.shutdown(wait=False, cancel_futures=True)
    service.root = tmp_path
    service.jobs_root = tmp_path / "jobs"
    service.jobs_root.mkdir(parents=True)
    service.store = DraftingLiteStore(tmp_path / "jobs.db", 24)
    service.store.initialize()
    service.executor = RecordingExecutor()
    return service


def _mock_evidence_pipeline(monkeypatch):
    result = evidence_directory.EvidenceDirectoryResult(
        status="placeholder",
        items=[],
        validation_issues=["no_verifiable_evidence"],
    )
    monkeypatch.setattr(
        evidence_directory,
        "extract_evidence_directory",
        lambda *args, **kwargs: result,
    )

    def fake_render_evidence(
        job_id, cause_label, plaintiff_name, evidence_result, jobs_root, template_root
    ):
        output = jobs_root / job_id / "output" / "证据目录.docx"
        output.write_bytes(b"evidence-docx")
        audit = output.parent / "evidence-directory-audit.json"
        audit.write_text("{}", encoding="utf-8")
        return output, output.name, audit

    monkeypatch.setattr(
        evidence_directory,
        "render_evidence_directory",
        fake_render_evidence,
    )

    def fake_render_package(
        job_id,
        cause_label,
        plaintiff_name,
        evidence_result,
        evidence_directory_path,
        manifest,
        jobs_root,
    ):
        output = jobs_root / job_id / "output" / "证据材料包.zip"
        output.write_bytes(b"zip")
        package_result = evidence_package.EvidenceMediaPackageResult(
            status="generated",
            items=[],
            package_filename=output.name,
            package_sha256="0" * 64,
        )
        audit = output.parent / "evidence-package-audit.json"
        audit.write_text("{}", encoding="utf-8")
        return output, output.name, package_result, audit

    monkeypatch.setattr(evidence_package, "render_evidence_package", fake_render_package)


def test_party_conflict_is_auto_resolved_without_confirmation_or_repeated_ocr(
    monkeypatch, tmp_path: Path
):
    service = _service(tmp_path)
    job_id = "workflow-party"
    service.store.create(job_id, "private_lending", [])
    cache_path = service.jobs_root / job_id / "output" / "parsed-materials.json"
    cache_path.parent.mkdir(parents=True)
    materials = [{
        "file_name": "起诉材料.pdf",
        "page_texts": [{
            "page_no": 1,
            "text": f"""原告：张三
身份证号码：{PLAINTIFF_ID}
地址：北京市旧地址1号
被告：李四
身份证号码：{DEFENDANT_ID}
地址：南京市测试路2号
原告：张某
身份证号码：{PLAINTIFF_ID}
地址：北京市旧地址1号
双方存在借款合同，尚欠本金4500元。""",
        }],
    }]
    cache_path.write_text(json.dumps(materials, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(party_extraction, "get_llm", lambda: InvalidJsonLLM())

    extraction_calls = 0
    real_extract = party_extraction.extract_parties

    def counted_extract(items):
        nonlocal extraction_calls
        extraction_calls += 1
        return real_extract(items)

    monkeypatch.setattr(party_extraction, "extract_parties", counted_extract)
    monkeypatch.setattr(
        material_agent,
        "extract_case_elements",
        lambda cause, items, warnings, schema: (
            {"claims.principal.amount": "4500元"},
            {
                "claims.principal.amount": [{
                    "source_type": "material",
                    "file_name": "起诉材料.pdf",
                    "page_no": 1,
                }]
            },
        ),
    )
    monkeypatch.setattr(research_agent, "retrieve_authorities", lambda cause, warnings, **kwargs: [])
    monkeypatch.setattr(
        drafting_agent,
        "draft",
        lambda cause, fields, provenance, items, cards, warnings: fields,
    )

    def fake_render(job, cause, values, jobs_root, store):
        output = jobs_root / job / "output" / "起诉状.docx"
        output.write_bytes(b"docx")
        return output, "起诉状.docx"

    monkeypatch.setattr(renderer, "render", fake_render)
    _mock_evidence_pipeline(monkeypatch)
    service._execute(job_id)

    completed = service.store.get(job_id)
    assert completed is not None
    assert completed["status"] == "completed"
    assert extraction_calls == 1
    assert completed["party_confirmed"] == 1
    assert [item["type"] for item in completed["output_artifacts"]] == [
        "complaint",
        "evidence_directory",
        "evidence_package",
    ]
    assert any(
        issue["code"] == "party_field_conflict"
        for issue in completed["party_issues"]
    )
    assert any("自动处理提示" in warning for warning in completed["warnings"])
    persisted = json.loads(
        (cache_path.parent / "extracted-elements.json").read_text(encoding="utf-8")
    )
    for field_id in (
        "party.plaintiff.name",
        "party.plaintiff.id_number",
        "party.plaintiff.address",
        "party.defendant.name",
        "party.defendant.id_number",
        "party.defendant.address",
    ):
        assert persisted["provenance"][field_id][0]["source_type"] == "material"
    assert persisted["fields"]["party.plaintiff.name"] == "张三"
    assert persisted["fields"]["party.plaintiff.id_type"] == "身份证"


def test_store_adds_party_columns_without_deleting_existing_jobs(tmp_path: Path):
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE drafting_lite_job (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, progress INTEGER NOT NULL,
                current_agent TEXT NOT NULL, cause_requested TEXT NOT NULL,
                cause_code TEXT, cause_label TEXT, confidence REAL, template_name TEXT,
                input_manifest TEXT NOT NULL, cause_evidence TEXT NOT NULL DEFAULT '[]',
                warnings TEXT NOT NULL DEFAULT '[]', authority_cards TEXT NOT NULL DEFAULT '[]',
                error_message TEXT, output_path TEXT, output_filename TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, expires_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO drafting_lite_job (
                id, status, progress, current_agent, cause_requested, input_manifest,
                created_at, updated_at, expires_at
            ) VALUES ('legacy-job', 'completed', 100, 'completed', 'private_lending',
                      '[]', '2026-01-01', '2026-01-01', '2099-01-01')
            """
        )

    store = DraftingLiteStore(database, 24)
    store.initialize()
    legacy = store.get("legacy-job")
    assert legacy is not None
    assert legacy["status"] == "completed"
    assert legacy["party_extraction"] == {}
    assert legacy["party_issues"] == []
    assert legacy["party_input_version"] == 0
    assert legacy["cause_candidates"] == []
    assert legacy["evidence_directory_result"] == {}
    assert legacy["evidence_package_result"] == {}
    assert legacy["output_artifacts"] == []
    assert legacy["artifact_contract_version"] == 1


def test_evidence_package_artifact_download_and_public_status(tmp_path: Path):
    service = _service(tmp_path)
    job_id = "package-download"
    service.store.create(job_id, "private_lending", [])
    assert service.store.get(job_id)["artifact_contract_version"] == 2
    output = service.jobs_root / job_id / "output" / "证据材料包.zip"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"PK-package")
    service.store.update(
        job_id,
        status="completed",
        evidence_package_result={
            "version": "evidence_media_package.v1",
            "status": "partial",
            "validation_issues": ["source_missing"],
        },
        output_artifacts=[
            {
                "type": "evidence_package",
                "filename": output.name,
                "path": str(output),
            }
        ],
    )

    path, filename = service.download_artifact(job_id, "evidence_package")
    public = _public_job(service.store.get(job_id) or {})

    assert path == output.resolve()
    assert filename == "证据材料包.zip"
    assert public["evidence_package_status"] == "partial"
    assert public["evidence_package_issues"] == ["source_missing"]
    assert public["artifacts"][0]["type"] == "evidence_package"


def test_legacy_complaint_download_and_package_download_use_correct_media_types(
    monkeypatch, tmp_path: Path
):
    complaint = tmp_path / "起诉状.docx"
    package = tmp_path / "证据材料包.zip"
    complaint.write_bytes(b"docx")
    package.write_bytes(b"zip")

    class FakeService:
        def download(self, job_id):
            return complaint, complaint.name

        def download_artifact(self, job_id, artifact_type):
            assert artifact_type == "evidence_package"
            return package, package.name

    monkeypatch.setattr(
        drafting_lite_api,
        "get_drafting_lite_service",
        lambda: FakeService(),
    )

    complaint_response = drafting_lite_api.download("job-1", None)
    package_response = drafting_lite_api.download_artifact(
        "job-1", "evidence_package", None
    )

    assert complaint_response.media_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert package_response.media_type == "application/zip"


def test_cancelled_job_is_terminal_and_rejects_late_worker_updates(tmp_path: Path):
    service = _service(tmp_path)
    service._started = True
    service.store.create("cancel-me", "auto", [])

    cancelled = service.cancel_job("cancel-me")

    assert cancelled["status"] == "cancelled"
    assert cancelled["current_agent"] == "cancelled"
    late = service.store.update(
        "cancel-me",
        status="completed",
        progress=100,
        current_agent="completed",
    )
    assert late["status"] == "cancelled"
    assert late["progress"] == 0
    with pytest.raises(RuntimeError, match="不能取消"):
        service.cancel_job("cancel-me")


def test_worker_stops_after_cancel_during_material_parsing(monkeypatch, tmp_path: Path):
    service = _service(tmp_path)
    job_id = "cancel-during-parse"
    service.store.create(job_id, "auto", [])

    def cancel_while_parsing(*args, **kwargs):
        service.store.cancel(job_id)
        return [{
            "file_name": "材料.md",
            "page_texts": [{"page_no": 1, "text": "案由：民间借贷纠纷"}],
        }]

    monkeypatch.setattr(material_agent, "parse_materials", cancel_while_parsing)
    monkeypatch.setattr(
        material_agent,
        "classify_cause",
        lambda *args, **kwargs: pytest.fail("取消后不应继续识别案由"),
    )

    service._execute(job_id)

    cancelled = service.store.get(job_id)
    assert cancelled is not None
    assert cancelled["status"] == "cancelled"


def test_python_cause_catalog_is_dynamic(monkeypatch):
    response = list_causes(None)
    codes = {item["code"] for item in response["items"]}
    assert len(codes) == 10
    assert {
        "trademark_infringement",
        "invention_patent_infringement",
    } <= codes

    monkeypatch.setitem(
        CAUSES,
        "future_cause",
        {
            "label": "未来案由",
            "template": "起诉状/未来案由.docx",
            "schema": "future_cause.v1.json",
        },
    )
    response = list_causes(None)
    assert any(item["code"] == "future_cause" for item in response["items"])


def test_startup_rejects_unknown_party_schema_fields(monkeypatch, tmp_path: Path):
    class Field:
        field_id = "party.plaintiff.future_secret_field"

    class Schema:
        fields = [Field()]

    service = _service(tmp_path)
    service._started = False
    monkeypatch.setattr(drafting_service, "load_schema", lambda path: Schema())
    with pytest.raises(RuntimeError, match="未知公共当事人字段"):
        service.startup()


@pytest.mark.parametrize("cause", sorted(CAUSES))
def test_all_ten_workflows_use_the_public_party_extractor(
    monkeypatch, tmp_path: Path, cause: str
):
    service = _service(tmp_path / cause)
    job_id = f"workflow-{cause}"
    service.store.create(job_id, cause, [])
    organization_defendant = cause in {
        "labor_dispute",
        "work_injury_insurance",
    }
    defendant_text = (
        """被告：示例科技有限公司
统一社会信用代码：91110000100000000A
地址：北京市海淀区创新路8号"""
        if organization_defendant
        else f"""被告：李四
身份证号码：{DEFENDANT_ID}
地址：南京市鼓楼区测试路2号"""
    )
    materials = [{
        "file_name": "起诉材料.pdf",
        "page_texts": [{
            "page_no": 1,
            "text": f"""原告：张三
身份证号码：{PLAINTIFF_ID}
地址：北京市东城区测试路1号
{defendant_text}
本页另载有与{CAUSES[cause]["label"]}相关的案件事实。""",
        }],
    }]
    cache = service.jobs_root / job_id / "output" / "parsed-materials.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps(materials, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(party_extraction, "get_llm", lambda: InvalidJsonLLM())

    calls = 0
    real_extract = party_extraction.extract_parties

    def counted_extract(items):
        nonlocal calls
        calls += 1
        return real_extract(items)

    monkeypatch.setattr(party_extraction, "extract_parties", counted_extract)
    monkeypatch.setattr(
        material_agent,
        "extract_case_elements",
        lambda selected_cause, items, warnings, schema: ({}, {}),
    )
    monkeypatch.setattr(research_agent, "retrieve_authorities", lambda selected_cause, warnings, **kwargs: [])
    monkeypatch.setattr(
        drafting_agent,
        "draft",
        lambda selected_cause, fields, provenance, items, cards, warnings: fields,
    )

    def fake_render(job, selected_cause, values, jobs_root, store):
        output = jobs_root / job / "output" / f"{selected_cause}.docx"
        output.write_bytes(b"docx")
        return output, output.name

    monkeypatch.setattr(renderer, "render", fake_render)
    _mock_evidence_pipeline(monkeypatch)
    service._execute(job_id)
    completed = service.store.get(job_id)
    assert completed is not None
    assert completed["status"] == "completed"
    assert calls == 1
    audit_path = (
        service.jobs_root / job_id / "output" / "request-basis-audit.json"
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["schema_version"] == "request_basis.v1"
    assert audit["status"] == "placeholder"
    assert audit["legal_text"] == "【待补充：未检索到可核验的请求依据】"
