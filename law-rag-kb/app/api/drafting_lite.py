from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import Principal, require_service_principal
from app.drafting_lite.service import CAUSES, get_drafting_lite_service

router = APIRouter(prefix="/drafting-lite", tags=["drafting-lite"])


class CauseSelection(BaseModel):
    cause: str


class PartyConfirmation(BaseModel):
    version: int
    parties: list[dict[str, Any]]
    confirmed: bool


def _public_job(job: dict) -> dict:
    manifest = job.get("input_manifest") or []
    source_kinds = {item.get("source_kind", "upload") for item in manifest}
    input_mode = (
        "mixed"
        if len(source_kinds) > 1
        else ("knowledge" if source_kinds == {"knowledge"} else "upload")
    )
    artifacts = [
        {
            "type": str(item.get("type")),
            "filename": str(
                item.get("filename")
                or ("证据材料包.zip" if item.get("type") == "evidence_package" else "文书.docx")
            ),
            "download_url": (
                f"/api/drafting-lite/jobs/{job['id']}/artifacts/"
                f"{item.get('type')}/download"
            ),
        }
        for item in (job.get("output_artifacts") or [])
        if job.get("status") == "completed"
        and isinstance(item, dict)
        and item.get("type") in {"complaint", "evidence_directory", "evidence_package"}
    ]
    return {
        "job_id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "current_agent": job["current_agent"],
        "cause_requested": job["cause_requested"],
        "cause_code": job.get("cause_code"),
        "cause_label": job.get("cause_label"),
        "confidence": job.get("confidence"),
        "template_name": job.get("template_name"),
        "cause_evidence": job.get("cause_evidence") or [],
        "cause_candidates": job.get("cause_candidates") or [],
        "party_extraction": job.get("party_extraction") or None,
        "party_issues": job.get("party_issues") or [],
        "party_confirmation_required": job["status"] == "waiting_party_confirmation",
        "party_input_version": int(job.get("party_input_version") or 0),
        "warnings": job.get("warnings") or [],
        "evidence_package_status": (
            (job.get("evidence_package_result") or {}).get("status") or None
        ),
        "evidence_package_issues": (
            (job.get("evidence_package_result") or {}).get("validation_issues") or []
        ),
        "error_message": job.get("error_message"),
        "download_url": (
            f"/api/drafting-lite/jobs/{job['id']}/download"
            if job["status"] == "completed"
            else None
        ),
        "artifacts": artifacts,
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "input_mode": input_mode,
        "selected_materials": [
            {
                "source_kind": item.get("source_kind", "upload"),
                "document_id": item.get("document_id"),
                "title": item.get("title") or item.get("name") or "当事人材料",
                "status": item.get("status") or "ready",
            }
            for item in manifest
        ],
    }


@router.get("/causes")
def list_causes(
    _: Annotated[Principal, Depends(require_service_principal)],
):
    return {
        "items": [
            {
                "code": code,
                "label": config["label"],
                "template_name": config["template"].split("/")[-1],
            }
            for code, config in CAUSES.items()
        ]
    }


@router.post("/jobs", status_code=202)
async def create_job(
    _: Annotated[Principal, Depends(require_service_principal)],
    files: Annotated[list[UploadFile] | None, File()] = None,
    knowledge_document_ids: Annotated[str, Form()] = "[]",
    cause: Annotated[str, Form()] = "auto",
):
    if not settings.drafting_lite_enabled:
        raise HTTPException(status_code=503, detail="独立文书生成功能未启用")
    payloads: list[tuple[str, bytes, str]] = []
    total = 0
    try:
        parsed_ids = json.loads(knowledge_document_ids)
        if not isinstance(parsed_ids, list):
            raise ValueError
        document_ids = [int(value) for value in parsed_ids]
        if any(value <= 0 for value in document_ids):
            raise ValueError
    except (TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="知识库材料参数格式无效") from None
    for upload in files or []:
        content = await upload.read(settings.drafting_lite_max_total_bytes + 1)
        total += len(content)
        if total > settings.drafting_lite_max_total_bytes:
            raise HTTPException(status_code=413, detail="上传文件总大小超过限制")
        payloads.append(
            (
                upload.filename or "material",
                content,
                upload.content_type or "application/octet-stream",
            )
        )
    try:
        return _public_job(
            get_drafting_lite_service().create_job(
                payloads,
                cause,
                knowledge_document_ids=document_ids,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    _: Annotated[Principal, Depends(require_service_principal)],
):
    job = get_drafting_lite_service().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return _public_job(job)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    _: Annotated[Principal, Depends(require_service_principal)],
):
    try:
        return _public_job(get_drafting_lite_service().cancel_job(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或已过期") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/cause")
def select_cause(
    job_id: str,
    body: CauseSelection,
    _: Annotated[Principal, Depends(require_service_principal)],
):
    try:
        return _public_job(get_drafting_lite_service().select_cause(job_id, body.cause))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或已过期") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/parties")
def confirm_parties(
    job_id: str,
    body: PartyConfirmation,
    _: Annotated[Principal, Depends(require_service_principal)],
):
    try:
        return _public_job(
            get_drafting_lite_service().confirm_parties(
                job_id,
                version=body.version,
                parties=body.parties,
                confirmed=body.confirmed,
            )
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或已过期") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/download")
def download(
    job_id: str,
    _: Annotated[Principal, Depends(require_service_principal)],
):
    try:
        path, filename = get_drafting_lite_service().download(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或已过期") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )


@router.get("/jobs/{job_id}/artifacts/{artifact_type}/download")
def download_artifact(
    job_id: str,
    artifact_type: str,
    _: Annotated[Principal, Depends(require_service_principal)],
):
    try:
        path, filename = get_drafting_lite_service().download_artifact(
            job_id,
            artifact_type,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或已过期") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=(
            "application/zip"
            if artifact_type == "evidence_package"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename=filename,
    )
