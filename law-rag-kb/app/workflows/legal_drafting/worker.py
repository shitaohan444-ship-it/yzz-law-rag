from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import signal
import threading
import time
from typing import Any

import httpx

from app.core.config import settings
from app.ingest.parser import UnsupportedFileTypeError, parse
from app.ingest import vl
from app.template_engine import load_schema
from app.workflows.legal_drafting.graph import build_graph
from app.workflows.legal_drafting.nodes import extract_material_elements
from app.workflows.legal_drafting.platform_client import PlatformClient
from app.workflows.legal_drafting.renderer_client import render_docx

logger = logging.getLogger("legal_drafting_worker")
_stop = threading.Event()

_NODE_PROGRESS = {
    "load_context": 5,
    "extract_elements": 22,
    "compute_values": 28,
    "detect_gaps": 35,
    "identify_issues": 42,
    "retrieve_authorities": 52,
    "create_writing_plan": 58,
    "draft_claims": 68,
    "draft_facts": 68,
    "draft_legal_basis": 68,
    "draft_evidence": 68,
    "assemble_sections": 73,
    "review_facts": 78,
    "review_law": 81,
    "review_evidence": 84,
    "review_template": 87,
    "review_expression": 90,
    "finalize_review": 92,
    "rewrite_sections": 86,
    "render_document": 96,
}


def _checkpointer_context():
    if settings.agent_database_url:
        from langgraph.checkpoint.postgres import PostgresSaver

        return PostgresSaver.from_conn_string(settings.agent_database_url)
    from langgraph.checkpoint.memory import MemorySaver

    class _MemoryContext:
        def __enter__(self):
            return MemorySaver()

        def __exit__(self, *_args):
            return False

    return _MemoryContext()


class HeartbeatLoop:
    def __init__(
        self,
        run_id: str,
        event_seq: int,
        worker_id: str,
        lease_seconds: int,
    ):
        self.run_id = run_id
        self.event_seq = event_seq
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.cancel_requested = False
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.stop_event.set()
        self.thread.join(timeout=5)

    def _run(self):
        interval = max(10.0, self.lease_seconds / 3)
        client = PlatformClient(
            settings.legal_drafting_platform_base_url,
            settings.legal_drafting_worker_token,
        )
        try:
            while not self.stop_event.wait(interval):
                try:
                    self.cancel_requested = client.heartbeat(
                        self.run_id,
                        self.worker_id,
                        self.event_seq,
                        self.lease_seconds,
                    )
                except Exception:
                    logger.exception("heartbeat failed for run %s", self.run_id)
        finally:
            client.close()


def _material_texts(
    client: PlatformClient,
    run_id: str,
    run_token: str,
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for material in snapshot.get("materials") or []:
        material_id = str(material.get("id") or "")
        attachment = material.get("attachment") or {}
        extension = str(attachment.get("file_ext") or "")
        if not extension:
            extension = Path(str(attachment.get("file_name") or "")).suffix
        if not material_id or not extension:
            continue
        content = client.material_content(run_id, material_id, run_token)
        try:
            document = parse(
                content,
                extension,
                scan_page_min_text_chars=settings.scan_page_min_text_chars,
                pdf_render_scale=settings.pdf_render_scale,
            )
        except UnsupportedFileTypeError:
            logger.warning("unsupported material type: material=%s ext=%s", material_id, extension)
            continue
        vision_pages, vision_status = _vision_text(document, material_id)
        page_text: dict[int | None, list[str]] = {}
        for block in document.text_blocks:
            if block.text.strip():
                page_text.setdefault(block.page_no, []).append(block.text.strip())
        for item in vision_pages:
            page_text.setdefault(item.get("page_no"), []).append(str(item["text"]))
        page_texts = [
            {"page_no": page_no, "text": "\n\n".join(parts)}
            for page_no, parts in sorted(
                page_text.items(), key=lambda item: (item[0] is None, item[0] or 0)
            )
        ]
        combined_text = "\n\n".join(
            str(item["text"]) for item in page_texts if str(item["text"]).strip()
        )
        output.append(
            {
                "material_id": material_id,
                "attachment_id": str(material.get("attachment_id") or ""),
                "content_hash": hashlib.sha256(content).hexdigest(),
                "text": combined_text,
                "page_texts": page_texts,
                "page_count": document.metadata.get("page_count"),
                "vision_status": vision_status,
            }
        )
    return output


def _vision_text(document, material_id: str) -> tuple[list[dict[str, Any]], str]:
    if not document.images:
        return [], "not_required"
    if any(image.is_page_scan for image in document.images) and not settings.vl_configured:
        raise RuntimeError(
            f"VL_NOT_CONFIGURED_FOR_SCANNED_MATERIAL: material={material_id}"
        )
    if not settings.vl_configured:
        return [], "not_configured"

    cache_root = (
        Path(settings.legal_drafting_output_root)
        / "vl-cache"
        / settings.vl_prompt_version
        / settings.vl_model.replace("/", "_")
    )
    cache_root.mkdir(parents=True, exist_ok=True)
    text_parts: list[dict[str, Any]] = []
    failures = 0
    for image in document.images:
        cache_path = cache_root / f"{image.sha256}.json"
        payload: dict[str, Any]
        try:
            if cache_path.exists():
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
            else:
                analysis = vl.analyze(
                    image,
                    doc_title=f"案件材料 {material_id}",
                    context_text=image.nearby_text,
                )
                payload = {
                    "status": analysis.status,
                    "category": analysis.category,
                    "description": analysis.description,
                    "extracted_text": analysis.extracted_text,
                    "page_no": image.page_no,
                    "content_hash": image.sha256,
                }
                temporary = cache_path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )
                temporary.replace(cache_path)
        except Exception as exc:
            failures += 1
            logger.warning(
                "VL analysis failed: material=%s page=%s error=%s",
                material_id,
                image.page_no,
                type(exc).__name__,
            )
            continue
        searchable = "\n".join(
            str(payload.get(key) or "").strip()
            for key in ("description", "extracted_text")
            if str(payload.get(key) or "").strip()
        )
        if searchable:
            text_parts.append(
                {
                    "page_no": image.page_no,
                    "text": f"[图像识别]\n{searchable}",
                }
            )
    if failures and not text_parts:
        return [], "failed"
    return text_parts, "partial" if failures else "success"


def _schema_path(template: dict[str, Any]) -> Path:
    template_code = str(template.get("template_code") or "")
    schema_names = {
        "civil_complaint.private_lending": "private_lending_complaint.v1.json",
        "civil_defense.trademark_infringement": "trademark_defense.v1.json",
    }
    schema_name = schema_names.get(template_code)
    if not schema_name:
        raise RuntimeError(f"TEMPLATE_SCHEMA_NOT_IMPLEMENTED: {template_code}")
    return Path(__file__).resolve().parents[2] / "template_engine" / "schemas" / schema_name


def _process_claim(client: PlatformClient, graph, claim: dict[str, Any]) -> None:
    run = claim["run"]
    run_id = str(run["id"])
    run_token = str(claim["run_token"])
    event_seq = int(run.get("event_seq") or 0)
    event_seq += 1
    client.event(
        run_id,
        event_seq=event_seq,
        event_type="worker_started",
        status="running",
        current_node="load_snapshot",
        progress=3,
    )
    with HeartbeatLoop(
        run_id,
        event_seq,
        settings.legal_drafting_worker_id,
        settings.legal_drafting_lease_seconds,
    ) as heartbeat:
        snapshot = client.snapshot(run_id, run_token)
        materials = _material_texts(client, run_id, run_token, snapshot)
        template = snapshot.get("template") or {}
        schema_path = _schema_path(template)
        schema = load_schema(schema_path)
        extracted, extracted_provenance, extraction_warnings = (
            extract_material_elements(
                materials,
                [
                    field.field_id
                    for field in schema.fields
                    if field.generation_policy in {"extract_only", "draft_with_sources"}
                ],
            )
        )
        del materials
        source_path = Path(settings.legal_drafting_template_root) / str(
            template.get("source_path") or ""
        )
        initial_state = {
            "run_id": run_id,
            "thread_id": str(run["thread_id"]),
            "snapshot": snapshot,
            "schema_path": str(schema_path),
            "template_source_path": str(source_path),
            "pre_extracted_elements": extracted,
            "pre_extracted_provenance": extracted_provenance,
            "extraction_warnings": extraction_warnings,
            "warnings": [],
        }
        graph_config = {
            "configurable": {"thread_id": str(run["thread_id"])}
        }
        for update in graph.stream(
            initial_state,
            config=graph_config,
            stream_mode="updates",
        ):
            for node_name in update:
                event_seq += 1
                client.event(
                    run_id,
                    event_seq=event_seq,
                    event_type="node_completed",
                    status="running",
                    current_node=node_name,
                    progress=_NODE_PROGRESS.get(node_name, 50),
                    payload={"node": node_name},
                )
            if heartbeat.cancel_requested:
                return
        result = dict(graph.get_state(graph_config).values)
        if heartbeat.cancel_requested:
            return

    event_seq += 1
    status = str(result.get("status") or "failed")
    if status == "waiting_user_input":
        client.event(
            run_id,
            event_seq=event_seq,
            event_type="workflow_interrupted",
            status="waiting_user_input",
            current_node=str(result.get("current_node") or "detect_gaps"),
            progress=45,
            payload={
                "missing_elements": result.get("missing_elements") or [],
                "conflicts": result.get("conflicts") or [],
                "review_issues": result.get("review_issues") or [],
            },
        )
        return
    if status != "pending_lawyer_review" or not result.get("docx_path"):
        raise RuntimeError(f"WORKFLOW_INVALID_FINAL_STATE: {status}")

    if not settings.legal_drafting_renderer_token:
        raise RuntimeError("LEGAL_DRAFTING_RENDERER_TOKEN is required")
    pdf_path, renderer_report = render_docx(
        settings.legal_drafting_renderer_url,
        settings.legal_drafting_renderer_token,
        result["docx_path"],
    )
    if renderer_report.get("residual_placeholders"):
        raise RuntimeError(
            f"RENDER_PLACEHOLDER_REMAINS: {renderer_report['residual_placeholders']}"
        )
    if renderer_report.get("blank_pages"):
        raise RuntimeError(f"RENDER_BLANK_PAGES: {renderer_report['blank_pages']}")

    artifact = client.persist_artifacts(
        run_id,
        run_token,
        result["docx_path"],
        {
            "title": f"{template.get('template_name') or '要素式法律文书'}（AI草稿）",
            "structured_document": result.get("structured_document") or {},
            "provenance": result.get("provenance") or {},
            "review_issues": result.get("review_issues") or [],
            "audit_report": {
                "render_report": {
                    **(result.get("render_report") or {}),
                    **renderer_report,
                },
                "warnings": result.get("warnings") or [],
                "ai_draft": True,
                "internal_trial": True,
            },
        },
        pdf_path,
    )
    client.event(
        run_id,
        event_seq=event_seq,
        event_type="workflow_completed",
        status="pending_lawyer_review",
        current_node="persist_result",
        progress=100,
        payload=artifact,
    )


def run_forever() -> None:
    if not settings.legal_drafting_enabled:
        logger.info("legal drafting worker disabled")
        return
    if not settings.legal_drafting_worker_token:
        raise RuntimeError("LEGAL_DRAFTING_WORKER_TOKEN is required")
    if not settings.agent_database_url:
        raise RuntimeError("AGENT_DATABASE_URL is required for durable checkpoints")
    logging.basicConfig(level=logging.INFO)
    client = PlatformClient(
        settings.legal_drafting_platform_base_url,
        settings.legal_drafting_worker_token,
    )
    with _checkpointer_context() as checkpointer:
        if hasattr(checkpointer, "setup"):
            checkpointer.setup()
        graph = build_graph(checkpointer=checkpointer)
        try:
            while not _stop.is_set():
                try:
                    claim = client.claim(
                        settings.legal_drafting_worker_id,
                        settings.legal_drafting_lease_seconds,
                    )
                    if claim:
                        try:
                            _process_claim(client, graph, claim)
                        except Exception as exc:
                            logger.exception("run processing failed")
                            run = claim["run"]
                            try:
                                latest = client.generation(str(run["id"]))
                                failure_event_seq = int(latest.get("event_seq") or 0) + 1
                            except Exception:
                                failure_event_seq = int(run.get("event_seq") or 0) + 1
                            client.event(
                                str(run["id"]),
                                event_seq=failure_event_seq,
                                event_type="workflow_failed",
                                status="failed",
                                current_node="worker",
                                error_code=type(exc).__name__[:80],
                                error_message=str(exc)[:4000],
                            )
                    else:
                        _stop.wait(settings.legal_drafting_poll_seconds)
                except httpx.HTTPError:
                    logger.exception("platform communication failed")
                    _stop.wait(settings.legal_drafting_poll_seconds)
        finally:
            client.close()


def _request_stop(*_args) -> None:
    _stop.set()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    run_forever()
