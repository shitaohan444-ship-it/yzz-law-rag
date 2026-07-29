from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import logging
from pathlib import Path
import re
import shutil
import threading
import time
from typing import Any
from uuid import uuid4

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
    material_agent,
    party_extraction,
    renderer,
    research_agent,
)
# Re-export for backward compatibility (api/drafting_lite.py, tests)
from app.drafting_lite.material_agent import _normalize_extracted_value  # noqa: F401

logger = logging.getLogger("uvicorn.error")


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
            for cause in CAUSES:
                self._schema_for_cause(cause)
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
        files: list[tuple[str, bytes]],
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
        total = sum(len(content) for _, content in files)
        if total > settings.drafting_lite_max_total_bytes:
            raise ValueError("上传文件总大小超过限制")
        job_id = uuid4().hex
        input_root = self.jobs_root / job_id / "input"
        input_root.mkdir(parents=True)
        manifest: list[dict[str, Any]] = []
        try:
            for index, (original_name, content) in enumerate(files, start=1):
                name = Path(original_name).name
                extension = Path(name).suffix.lower()
                if extension not in {".pdf", ".docx", ".doc"}:
                    raise ValueError(f"不支持的文件格式：{name}")
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

    def download(self, job_id: str) -> tuple[Path, str]:
        job = self.store.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job["status"] != "completed" or not job.get("output_path"):
            raise RuntimeError("文书尚未生成完成")
        path = Path(str(job["output_path"])).resolve()
        expected = (self.jobs_root / job_id).resolve()
        if expected not in path.parents or not path.is_file():
            raise RuntimeError("生成文件不存在")
        return path, str(job.get("output_filename") or "要素式起诉状.docx")

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
        return schema


    def _execute(self, job_id: str) -> None:
        warnings: list[str] = []
        try:
            job = self.store.get(job_id)
            if not job:
                return
            warnings = list(job.get("warnings") or [])
            self.store.update(job_id, status="parsing", progress=10, current_agent="material_agent")
            materials = material_agent.parse_materials(job_id, job["input_manifest"], warnings, self.jobs_root, self.store)
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
                warnings.extend(party_result.get("warnings") or [])
                job = self.store.update(
                    job_id,
                    party_extraction=party_result,
                    party_issues=party_result.get("issues") or [],
                    party_input_version=int(job.get("party_input_version") or 0) + 1,
                    warnings=warnings,
                )

            self.store.update(job_id, status="matching_cause", progress=30, current_agent="material_agent")
            if job["cause_requested"] == "auto":
                cause_result = material_agent.classify_cause(materials, combined_text)
                cause = cause_result.get("cause_code")
                confidence = float(cause_result.get("confidence") or 0)
                evidence = cause_result.get("evidence") or []
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
                        warnings=[*warnings, cause_warning],
                    )
                    return
            else:
                cause = str(job["cause_requested"])
                confidence = 1.0
                evidence = [{"file_name": "用户选择", "page_no": None, "reason": "手工指定案由"}]

            config = CAUSES[cause]
            job = self.store.update(
                job_id,
                cause_code=cause,
                cause_label=config["label"],
                confidence=confidence,
                cause_evidence=evidence,
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

            case_fields, case_provenance = material_agent.extract_case_elements(
                cause,
                materials,
                warnings,
                schema,
            )
            fields = {**party_values, **case_fields}
            provenance = {**party_provenance, **case_provenance}
            material_agent.persist_extraction(job_id, fields, provenance, self.jobs_root, self.store)

            self.store.update(job_id, status="retrieving_laws", progress=52, current_agent="research_agent")
            cards = research_agent.retrieve_authorities(cause, warnings)
            self.store.update(job_id, authority_cards=cards, warnings=warnings)

            self.store.update(job_id, status="drafting", progress=70, current_agent="drafting_agent")
            values = drafting_agent.draft(cause, fields, provenance, materials, cards, warnings)

            self.store.update(job_id, status="rendering", progress=88, current_agent="renderer", warnings=warnings)
            output, filename = renderer.render(job_id, cause, values, self.jobs_root, self.store)
            self.store.update(
                job_id,
                status="completed",
                progress=100,
                current_agent="completed",
                warnings=warnings,
                output_path=str(output),
                output_filename=filename,
                error_message=None,
            )
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
