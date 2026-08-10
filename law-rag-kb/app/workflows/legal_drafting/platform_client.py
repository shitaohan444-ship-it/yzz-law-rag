from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx


class PlatformClient:
    def __init__(self, base_url: str, worker_token: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.worker_token = worker_token
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout)

    @property
    def _worker_headers(self) -> dict[str, str]:
        return {"x-legal-worker-token": self.worker_token}

    def close(self) -> None:
        self.client.close()

    def claim(self, worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
        response = self.client.post(
            "/internal/legal-drafting/claims",
            headers=self._worker_headers,
            json={"worker_id": worker_id, "lease_seconds": lease_seconds},
        )
        response.raise_for_status()
        payload = response.json()
        return payload if payload.get("run") else None

    def heartbeat(
        self, run_id: str, worker_id: str, event_seq: int, lease_seconds: int
    ) -> bool:
        response = self.client.post(
            f"/internal/legal-drafting/runs/{run_id}/heartbeat",
            headers=self._worker_headers,
            json={
                "worker_id": worker_id,
                "event_seq": event_seq,
                "lease_seconds": lease_seconds,
            },
        )
        response.raise_for_status()
        return bool(response.json().get("cancel_requested"))

    def snapshot(self, run_id: str, run_token: str) -> dict[str, Any]:
        response = self.client.get(
            f"/internal/legal-drafting/runs/{run_id}/case-snapshot",
            headers={**self._worker_headers, "x-legal-run-token": run_token},
        )
        response.raise_for_status()
        return response.json()

    def generation(self, run_id: str) -> dict[str, Any]:
        response = self.client.get(f"/api/legal-document-generations/{run_id}")
        response.raise_for_status()
        return response.json()

    def material_content(
        self, run_id: str, material_id: str, run_token: str
    ) -> bytes:
        response = self.client.get(
            f"/internal/legal-drafting/runs/{run_id}/materials/{material_id}/content",
            headers={**self._worker_headers, "x-legal-run-token": run_token},
        )
        response.raise_for_status()
        return response.content

    def event(
        self,
        run_id: str,
        *,
        event_seq: int,
        event_type: str,
        status: str | None = None,
        current_node: str | None = None,
        progress: int | None = None,
        payload: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "event_seq": event_seq,
            "event_type": event_type,
            "payload": payload or {},
        }
        for key, value in (
            ("status", status),
            ("current_node", current_node),
            ("progress", progress),
            ("error_code", error_code),
            ("error_message", error_message),
        ):
            if value is not None:
                body[key] = value
        response = self.client.post(
            f"/internal/legal-drafting/runs/{run_id}/events",
            headers=self._worker_headers,
            json=body,
        )
        response.raise_for_status()
        return response.json()

    def persist_artifacts(
        self,
        run_id: str,
        run_token: str,
        docx_path: str | Path,
        metadata: dict[str, Any],
        pdf_path: str | Path | None = None,
    ) -> dict[str, Any]:
        docx = Path(docx_path)
        files: dict[str, tuple[str, bytes, str]] = {
            "docx": (
                docx.name,
                docx.read_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        }
        if pdf_path:
            pdf = Path(pdf_path)
            if pdf.exists():
                files["pdf"] = (pdf.name, pdf.read_bytes(), "application/pdf")
        response = self.client.post(
            f"/internal/legal-drafting/runs/{run_id}/artifacts",
            headers={**self._worker_headers, "x-legal-run-token": run_token},
            files=files,
            data={"metadata": json.dumps(metadata, ensure_ascii=False)},
            timeout=180,
        )
        response.raise_for_status()
        return response.json()
