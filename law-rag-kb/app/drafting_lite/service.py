from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
from io import BytesIO
import json
import logging
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
from typing import Any
from uuid import uuid4
import zipfile

import httpx
from sqlalchemy import bindparam, text

from app.core.config import settings
from app.core.database import SessionLocal
from app.rag.llm import LLMServiceError, get_llm
from app.template_engine import compile_template, load_schema, render_template
from app.drafting_lite.config import (
    AUTHORITY_KEYWORDS,
    CAUSE_FIELDS,
    CAUSES,
    COMMON_FIELDS,
    UNSUPPORTED_DOMAIN_KEYWORDS,
)
from app.drafting_lite.store import DraftingLiteStore
from app.drafting_lite import (
    drafting_agent,
    evidence_directory,
    evidence_package,
    material_agent,
    party_extraction,
    request_basis_agent,
    renderer,
    research_agent,
)
# Re-export for backward compatibility (api/drafting_lite.py, tests)
from app.drafting_lite.material_agent import _normalize_extracted_value  # noqa: F401

logger = logging.getLogger("uvicorn.error")


class DraftingCancelled(Exception):
    pass


_UPLOAD_MIME_TYPES = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".doc": {"application/msword", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    ".jpg": {"image/jpeg", "application/octet-stream"},
    ".jpeg": {"image/jpeg", "application/octet-stream"},
    ".png": {"image/png", "application/octet-stream"},
}


def _validate_upload_content(name: str, content: bytes, mime_type: str) -> str:
    extension = Path(name).suffix.lower()
    if extension not in _UPLOAD_MIME_TYPES:
        raise ValueError(f"不支持的文件格式：{name}")
    normalized_mime = mime_type.lower().split(";", 1)[0].strip()
    if normalized_mime and normalized_mime not in _UPLOAD_MIME_TYPES[extension]:
        raise ValueError(f"文件类型与扩展名不一致：{name}")
    valid = False
    if extension == ".pdf":
        valid = content.startswith(b"%PDF-")
    elif extension == ".doc":
        valid = content.startswith(bytes.fromhex("D0CF11E0"))
    elif extension == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist())
                valid = "[Content_Types].xml" in names and "word/document.xml" in names
        except zipfile.BadZipFile:
            valid = False
    elif extension in {".jpg", ".jpeg"}:
        valid = content.startswith(b"\xff\xd8\xff")
    elif extension == ".png":
        valid = content.startswith(b"\x89PNG\r\n\x1a\n")
    if not valid:
        raise ValueError(f"文件内容与扩展名不一致：{name}")
    return extension


class DraftingLiteService:
    def __init__(self) -> None:
        self.root = Path(settings.drafting_lite_data_root)
        self.jobs_root = self.root / "jobs"
        self.store = DraftingLiteStore(
            self.root / "jobs.db", settings.drafting_lite_retention_hours
        )
        self.executor = ThreadPoolExecutor(
            max_workers=settings.drafting_lite_workers,
            thread_name_prefix="drafting-lite",
        )
        self._started = False
        self._lock = threading.Lock()

    def startup(self) -> None:
        with self._lock:
            if self._started:
                return
            template_root = Path(settings.drafting_lite_template_root)
            with tempfile.TemporaryDirectory(prefix="drafting-lite-startup-") as temp_root:
                compiled_root = Path(temp_root)
                for cause, config in CAUSES.items():
                    schema = self._schema_for_cause(cause)
                    compile_template(
                        template_root / str(config["template"]),
                        compiled_root / f"{cause}.docx",
                        schema,
                    )
            evidence_directory.validate_evidence_directory_template(template_root)
            self.jobs_root.mkdir(parents=True, exist_ok=True)
            self.store.initialize()
            self.store.mark_interrupted()
            self.cleanup_expired()
            self._started = True

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)

    def cleanup_expired(self) -> None:
        for job in self.store.expired():
            shutil.rmtree(self.jobs_root / str(job["id"]), ignore_errors=True)
            self.store.delete(str(job["id"]))

    def create_job(
        self,
        files: list[tuple],
        cause: str,
        *,
        knowledge_document_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        self.startup()
        self.cleanup_expired()
        document_ids = sorted(set(knowledge_document_ids or []))
        if cause != "auto" and cause not in CAUSES:
            raise ValueError("不支持的案由")
        if not files and not document_ids:
            raise ValueError("请至少选择或上传一份当事人材料")
        if (
            len(files) + len(document_ids) > settings.drafting_lite_max_files
            or any(document_id <= 0 for document_id in document_ids)
        ):
            raise ValueError(f"一次任务最多选择{settings.drafting_lite_max_files}份材料")
        total = sum(len(item[1]) for item in files)
        if total > settings.drafting_lite_max_total_bytes:
            raise ValueError("上传文件总大小超过限制")
        job_id = uuid4().hex
        input_root = self.jobs_root / job_id / "input"
        input_root.mkdir(parents=True)
        manifest: list[dict[str, Any]] = []
        try:
            for index, item in enumerate(files, start=1):
                original_name, content = item[0], item[1]
                mime_type = str(item[2] if len(item) > 2 else "application/octet-stream")
                name = Path(original_name).name
                extension = _validate_upload_content(name, content, mime_type)
                stored_name = f"{index:02d}-{uuid4().hex[:8]}{extension}"
                path = input_root / stored_name
                path.write_bytes(content)
                manifest.append(
                    {
                        "source_kind": "upload",
                        "name": name,
                        "title": name,
                        "stored_name": stored_name,
                        "size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "mime_type": mime_type,
                        "status": "ready",
                    }
                )
            manifest.extend(
                material_agent.snapshot_knowledge_materials(job_id, input_root, document_ids)
            )
        except Exception:
            shutil.rmtree(self.jobs_root / job_id, ignore_errors=True)
            raise
        job = self.store.create(job_id, cause, manifest)
        self.executor.submit(self._execute, job_id)
        return job

    def select_cause(self, job_id: str, cause: str) -> dict[str, Any]:
        if cause not in CAUSES:
            raise ValueError("不支持的案由")
        job = self.store.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job["status"] != "waiting_cause_selection":
            raise RuntimeError("当前任务不等待案由选择")
        self.store.update(
            job_id,
            cause_requested=cause,
            status="queued",
            progress=0,
            current_agent="coordinator",
            cause_code=None,
            cause_label=None,
            confidence=None,
            template_name=None,
            cause_evidence=[],
            cause_candidates=[],
            error_message=None,
        )
        self.executor.submit(self._execute, job_id)
        return self.store.get(job_id) or {}

    def confirm_parties(
        self,
        job_id: str,
        *,
        version: int,
        parties: list[dict[str, Any]],
        confirmed: bool,
    ) -> dict[str, Any]:
        if not confirmed:
            raise ValueError("请确认当事人信息后继续")
        job = self.store.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job["status"] != "waiting_party_confirmation":
            raise RuntimeError("当前任务不等待当事人确认")
        current_version = int(job.get("party_input_version") or 0)
        if version != current_version:
            raise RuntimeError("当事人信息已更新，请刷新后重新确认")
        cause = str(job.get("cause_code") or job.get("cause_requested") or "")
        if cause not in CAUSES:
            raise RuntimeError("请先确认案由")
        result = party_extraction.normalize_confirmed_parties(
            parties,
            job.get("party_extraction") or {},
        )
        schema = self._schema_for_cause(cause)
        _, _, issues = party_extraction.project_parties(result, schema)
        next_version = current_version + 1
        if issues:
            return self.store.update(
                job_id,
                party_extraction=result,
                party_issues=issues,
                party_input_version=next_version,
                party_confirmed=0,
            )
        updated = self.store.update(
            job_id,
            status="queued",
            progress=40,
            current_agent="coordinator",
            party_extraction=result,
            party_issues=[],
            party_input_version=next_version,
            party_confirmed=1,
            error_message=None,
        )
        self.executor.submit(self._execute, job_id)
        return updated

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        self.startup()
        self.cleanup_expired()
        return self.store.get(job_id)

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        self.startup()
        return self.store.cancel(job_id)

    def download(self, job_id: str) -> tuple[Path, str]:
        return self.download_artifact(job_id, "complaint")

    def download_artifact(self, job_id: str, artifact_type: str) -> tuple[Path, str]:
        if artifact_type not in {"complaint", "evidence_directory", "evidence_package"}:
            raise ValueError("不支持的文书产物类型")
        job = self.store.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job["status"] != "completed":
            raise RuntimeError("文书尚未生成完成")
        artifact = next(
            (
                item
                for item in (job.get("output_artifacts") or [])
                if isinstance(item, dict) and item.get("type") == artifact_type
            ),
            None,
        )
        if not artifact:
            raise RuntimeError("该文书产物不存在")
        path = Path(str(artifact.get("path") or "")).resolve()
        expected = (self.jobs_root / job_id).resolve()
        if expected not in path.parents or not path.is_file():
            raise RuntimeError("生成文件不存在")
        default_name = {
            "complaint": "要素式起诉状.docx",
            "evidence_directory": "证据目录.docx",
            "evidence_package": "证据材料包.zip",
        }[artifact_type]
        return path, str(artifact.get("filename") or default_name)

    @staticmethod
    def _schema_for_cause(cause: str):
        config = CAUSES[cause]
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "template_engine"
            / "schemas"
            / str(config["schema"])
        )
        schema = load_schema(schema_path)
        unknown = party_extraction.validate_template_party_fields(schema)
        if unknown:
            raise RuntimeError(f"模板包含未知公共当事人字段：{unknown}")
        request_basis_agent.validate_request_basis_schema(schema)
        evidence_directory.validate_evidence_directory_schema(schema)
        return schema

    def _raise_if_cancelled(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job and job.get("status") == "cancelled":
            raise DraftingCancelled(job_id)

    def _execute(self, job_id: str) -> None:
        warnings: list[str] = []
        try:
            job = self.store.get(job_id)
            if not job:
                return
            self._raise_if_cancelled(job_id)
            warnings = list(job.get("warnings") or [])
            self.store.update(job_id, status="parsing", progress=10, current_agent="material_agent")
            materials = material_agent.parse_materials(job_id, job["input_manifest"], warnings, self.jobs_root, self.store)
            self._raise_if_cancelled(job_id)
            combined_text = "\n\n".join(
                page["text"] for item in materials for page in item["page_texts"] if page["text"]
            )
            if not combined_text.strip():
                raise ValueError("未能从所选或上传材料中识别出可用文字")

            party_result = job.get("party_extraction") or {}
            if not party_result.get("schema_version"):
                self.store.update(
                    job_id,
                    status="parsing",
                    progress=28,
                    current_agent="party_agent",
                )
                party_result = party_extraction.extract_parties(materials)
                self._raise_if_cancelled(job_id)
                warnings.extend(party_result.get("warnings") or [])
                job = self.store.update(
                    job_id,
                    party_extraction=party_result,
                    party_issues=party_result.get("issues") or [],
                    party_input_version=int(job.get("party_input_version") or 0) + 1,
                    warnings=warnings,
                )

            self._raise_if_cancelled(job_id)
            self.store.update(job_id, status="matching_cause", progress=30, current_agent="material_agent")
            if job["cause_requested"] == "auto":
                cause_result = material_agent.classify_cause(materials, combined_text)
                self._raise_if_cancelled(job_id)
                cause = cause_result.get("cause_code")
                confidence = float(cause_result.get("confidence") or 0)
                evidence = cause_result.get("evidence") or []
                candidates = cause_result.get("candidates") or []
                if cause not in CAUSES or confidence < settings.drafting_lite_cause_threshold:
                    out_of_scope = any(
                        str(item.get("reason") or "").startswith("疑似")
                        for item in evidence
                        if isinstance(item, dict)
                    )
                    cause_warning = (
                        "材料疑似不属于当前已配置的起诉状案由，"
                        "系统已停止套用错误模板；请核实案由后再手工覆盖"
                        if out_of_scope
                        else "材料不足以可靠判断案由，请手工选择后继续"
                    )
                    self.store.update(
                        job_id,
                        status="waiting_cause_selection",
                        progress=35,
                        current_agent="material_agent",
                        confidence=confidence,
                        cause_evidence=evidence,
                        cause_candidates=candidates,
                        warnings=[*warnings, cause_warning],
                    )
                    return
            else:
                cause = str(job["cause_requested"])
                confidence = 1.0
                evidence = [{"file_name": "用户选择", "page_no": None, "reason": "手工指定案由"}]
                candidates = [{
                    "cause_code": cause,
                    "label": str(CAUSES[cause]["label"]),
                    "confidence": 1.0,
                }]

            config = CAUSES[cause]
            job = self.store.update(
                job_id,
                cause_code=cause,
                cause_label=config["label"],
                confidence=confidence,
                cause_evidence=evidence,
                cause_candidates=candidates,
                template_name=Path(config["template"]).name,
            )
            schema = self._schema_for_cause(cause)
            party_values, party_provenance, party_issues = (
                party_extraction.project_parties(party_result, schema)
            )
            if party_issues:
                for issue in party_issues:
                    warning = f"当事人信息自动处理提示：{issue.get('message') or issue.get('code')}"
                    if warning not in warnings:
                        warnings.append(warning)
                self.store.update(
                    job_id,
                    status="parsing",
                    progress=42,
                    current_agent="party_agent",
                    party_issues=party_issues,
                    party_confirmed=1,
                    warnings=warnings,
                )
            else:
                self.store.update(
                    job_id,
                    party_issues=[],
                    party_confirmed=1,
                    warnings=warnings,
                )

            self._raise_if_cancelled(job_id)
            case_fields, case_provenance = material_agent.extract_case_elements(
                cause,
                materials,
                warnings,
                schema,
            )
            self._raise_if_cancelled(job_id)
            fields = {**party_values, **case_fields}
            provenance = {**party_provenance, **case_provenance}
            material_agent.persist_extraction(job_id, fields, provenance, self.jobs_root, self.store)

            self.store.update(job_id, status="retrieving_laws", progress=52, current_agent="research_agent")
            self._raise_if_cancelled(job_id)
            cards = research_agent.retrieve_authorities(
                cause,
                warnings,
                fields=fields,
                provenance=provenance,
            )
            self._raise_if_cancelled(job_id)
            self.store.update(job_id, authority_cards=cards, warnings=warnings)

            self.store.update(job_id, status="drafting", progress=70, current_agent="drafting_agent")
            self._raise_if_cancelled(job_id)
            values = drafting_agent.draft(cause, fields, provenance, materials, cards, warnings)
            # 撰写阶段会补齐可由材料或已核验字段支持的 Schema 字段；再次持久化，
            # 确保后续请求依据、审计和失败重试都使用完整字段集。
            material_agent.persist_extraction(
                job_id, fields, provenance, self.jobs_root, self.store
            )
            self._raise_if_cancelled(job_id)
            request_basis_result = request_basis_agent.draft_request_basis(
                cause,
                schema,
                values,
                fields,
                provenance,
                materials,
                cards,
                warnings,
            )
            values, legal_text, contractual_text = (
                request_basis_agent.apply_request_basis(
                    schema,
                    values,
                    request_basis_result,
                    cards,
                )
            )
            request_basis_agent.persist_request_basis_audit(
                job_id,
                self.jobs_root,
                request_basis_result,
                legal_text,
                contractual_text,
                cards,
            )
            self._raise_if_cancelled(job_id)

            self.store.update(job_id, status="rendering", progress=82, current_agent="renderer", warnings=warnings)
            self._raise_if_cancelled(job_id)
            output, filename = renderer.render(job_id, cause, values, self.jobs_root, self.store)
            self._raise_if_cancelled(job_id)
            complaint_artifact = {
                "type": "complaint",
                "filename": filename,
                "path": str(output),
            }
            self.store.update(
                job_id,
                status="drafting_evidence",
                progress=90,
                current_agent="evidence_agent",
                warnings=warnings,
                output_path=str(output),
                output_filename=filename,
                output_artifacts=[complaint_artifact],
                error_message=None,
            )
            self._raise_if_cancelled(job_id)
            evidence_result = evidence_directory.extract_evidence_directory(
                materials,
                fields,
                provenance,
                str(values.get("document.claims") or ""),
                warnings,
            )
            self.store.update(
                job_id,
                status="rendering_evidence",
                progress=96,
                current_agent="evidence_renderer",
                evidence_directory_result=evidence_result.model_dump(mode="json"),
                warnings=warnings,
            )
            self._raise_if_cancelled(job_id)
            plaintiff = str(
                values.get("party.plaintiff.name")
                or values.get("party.plaintiff.organization_name")
                or "当事人"
            )
            evidence_output, evidence_filename, _ = (
                evidence_directory.render_evidence_directory(
                    job_id,
                    str(config["label"]),
                    plaintiff,
                    evidence_result,
                    self.jobs_root,
                    Path(settings.drafting_lite_template_root),
                )
            )
            self._raise_if_cancelled(job_id)
            evidence_artifact = {
                "type": "evidence_directory",
                "filename": evidence_filename,
                "path": str(evidence_output),
            }
            self.store.update(
                job_id,
                status="collecting_evidence_media",
                progress=97,
                current_agent="evidence_media_collector",
                warnings=warnings,
                evidence_directory_result=evidence_result.model_dump(mode="json"),
                output_artifacts=[complaint_artifact, evidence_artifact],
                error_message=None,
            )
            self._raise_if_cancelled(job_id)
            self.store.update(
                job_id,
                status="packaging_evidence",
                progress=99,
                current_agent="evidence_packager",
            )
            package_output, package_filename, package_result, _ = (
                evidence_package.render_evidence_package(
                    job_id,
                    str(config["label"]),
                    plaintiff,
                    evidence_result,
                    evidence_output,
                    list(job.get("input_manifest") or []),
                    self.jobs_root,
                )
            )
            self._raise_if_cancelled(job_id)
            package_artifact = {
                "type": "evidence_package",
                "filename": package_filename,
                "path": str(package_output),
            }
            if package_result.status == "partial":
                warnings.append("部分证据材料未能取得原件，压缩包内已附缺失说明。")
            self.store.update(
                job_id,
                status="completed",
                progress=100,
                current_agent="completed",
                warnings=warnings,
                evidence_package_result=package_result.model_dump(mode="json"),
                output_artifacts=[complaint_artifact, evidence_artifact, package_artifact],
                error_message=None,
            )
        except DraftingCancelled:
            logger.info("drafting_lite cancelled job_id=%s", job_id)
            return
        except Exception as exc:
            logger.exception("drafting_lite failed job_id=%s type=%s", job_id, type(exc).__name__)
            try:
                self.store.update(
                    job_id,
                    status="failed",
                    progress=0,
                    current_agent="failed",
                    warnings=warnings,
                    error_message=self._safe_error(exc),
                )
            except Exception:
                logger.exception("drafting_lite could not persist failure job_id=%s", job_id)

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, ValueError):
            return str(exc)[:500]
        if isinstance(exc, LLMServiceError):
            return "大模型服务暂时不可用，请稍后重试"
        return f"生成失败（{type(exc).__name__}），请检查服务日志"


_service: DraftingLiteService | None = None


def get_drafting_lite_service() -> DraftingLiteService:
    global _service
    if _service is None:
        _service = DraftingLiteService()
    return _service
