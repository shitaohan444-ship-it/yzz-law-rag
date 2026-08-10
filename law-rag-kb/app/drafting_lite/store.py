from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any


CURRENT_ARTIFACT_CONTRACT_VERSION = 2


ACTIVE_STATUSES = {
    "queued",
    "parsing",
    "matching_cause",
    "retrieving_laws",
    "drafting",
    "rendering",
    "drafting_evidence",
    "rendering_evidence",
    "collecting_evidence_media",
    "packaging_evidence",
}
JSON_COLUMNS = {
    "input_manifest",
    "cause_evidence",
    "cause_candidates",
    "warnings",
    "authority_cards",
    "party_extraction",
    "party_issues",
    "evidence_directory_result",
    "evidence_package_result",
    "output_artifacts",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DraftingLiteStore:
    def __init__(self, database_path: Path, retention_hours: int):
        self.database_path = database_path
        self.retention_hours = retention_hours

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS drafting_lite_job (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    current_agent TEXT NOT NULL,
                    cause_requested TEXT NOT NULL,
                    cause_code TEXT,
                    cause_label TEXT,
                    confidence REAL,
                    template_name TEXT,
                    input_manifest TEXT NOT NULL,
                    cause_evidence TEXT NOT NULL DEFAULT '[]',
                    cause_candidates TEXT NOT NULL DEFAULT '[]',
                    warnings TEXT NOT NULL DEFAULT '[]',
                    authority_cards TEXT NOT NULL DEFAULT '[]',
                    party_extraction TEXT NOT NULL DEFAULT '{}',
                    party_issues TEXT NOT NULL DEFAULT '[]',
                    party_input_version INTEGER NOT NULL DEFAULT 0,
                    party_confirmed INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    output_path TEXT,
                    output_filename TEXT,
                    evidence_directory_result TEXT NOT NULL DEFAULT '{}',
                    evidence_package_result TEXT NOT NULL DEFAULT '{}',
                    output_artifacts TEXT NOT NULL DEFAULT '[]',
                    artifact_contract_version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            existing = {
                str(row[1])
                for row in db.execute("PRAGMA table_info(drafting_lite_job)").fetchall()
            }
            additions = {
                "party_extraction": "TEXT NOT NULL DEFAULT '{}'",
                "party_issues": "TEXT NOT NULL DEFAULT '[]'",
                "party_input_version": "INTEGER NOT NULL DEFAULT 0",
                "party_confirmed": "INTEGER NOT NULL DEFAULT 0",
                "cause_candidates": "TEXT NOT NULL DEFAULT '[]'",
                "evidence_directory_result": "TEXT NOT NULL DEFAULT '{}'",
                "evidence_package_result": "TEXT NOT NULL DEFAULT '{}'",
                "output_artifacts": "TEXT NOT NULL DEFAULT '[]'",
                "artifact_contract_version": "INTEGER NOT NULL DEFAULT 1",
            }
            for column, declaration in additions.items():
                if column not in existing:
                    db.execute(
                        f"ALTER TABLE drafting_lite_job ADD COLUMN {column} {declaration}"
                    )

    def create(self, job_id: str, cause_requested: str, input_manifest: list[dict]) -> dict:
        now = _now()
        expires = now + timedelta(hours=self.retention_hours)
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO drafting_lite_job (
                    id, status, progress, current_agent, cause_requested,
                    input_manifest, artifact_contract_version,
                    created_at, updated_at, expires_at
                ) VALUES (?, 'queued', 0, 'coordinator', ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    cause_requested,
                    json.dumps(input_manifest, ensure_ascii=False),
                    CURRENT_ARTIFACT_CONTRACT_VERSION,
                    now.isoformat(),
                    now.isoformat(),
                    expires.isoformat(),
                ),
            )
        return self.get(job_id) or {}

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM drafting_lite_job WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        for key in JSON_COLUMNS:
            result[key] = json.loads(result.get(key) or "[]")
        if not result.get("output_artifacts") and result.get("output_path"):
            result["output_artifacts"] = [
                {
                    "type": "complaint",
                    "filename": result.get("output_filename") or "要素式起诉状.docx",
                    "path": result["output_path"],
                }
            ]
        return result

    def update(self, job_id: str, **values: Any) -> dict[str, Any]:
        allowed = {
            "status", "progress", "current_agent", "cause_requested", "cause_code",
            "cause_label", "confidence", "template_name", "cause_evidence", "warnings",
            "cause_candidates",
            "authority_cards", "error_message", "output_path", "output_filename",
            "party_extraction", "party_issues", "party_input_version", "party_confirmed",
            "evidence_directory_result", "evidence_package_result", "output_artifacts",
        }
        invalid = set(values) - allowed
        if invalid:
            raise ValueError(f"unsupported job columns: {sorted(invalid)}")
        if not values:
            return self.get(job_id) or {}
        encoded = {
            key: json.dumps(value, ensure_ascii=False) if key in JSON_COLUMNS else value
            for key, value in values.items()
        }
        encoded["updated_at"] = _now().isoformat()
        assignments = ", ".join(f"{key} = ?" for key in encoded)
        with self._connect() as db:
            status = values.get("status")
            protect_cancelled = status != "cancelled"
            db.execute(
                (
                    f"UPDATE drafting_lite_job SET {assignments} WHERE id = ?"
                    + (" AND status != 'cancelled'" if protect_cancelled else "")
                ),
                (*encoded.values(), job_id),
            )
        result = self.get(job_id)
        if result is None:
            raise KeyError(job_id)
        return result

    def cancel(self, job_id: str) -> dict[str, Any]:
        now = _now().isoformat()
        terminal = ("completed", "failed", "cancelled")
        with self._connect() as db:
            cursor = db.execute(
                """
                UPDATE drafting_lite_job
                   SET status = 'cancelled', current_agent = 'cancelled',
                       error_message = NULL, updated_at = ?
                 WHERE id = ? AND status NOT IN (?, ?, ?)
                """,
                (now, job_id, *terminal),
            )
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if cursor.rowcount == 0:
            raise RuntimeError("当前任务不能取消")
        return job

    def mark_interrupted(self) -> None:
        now = _now().isoformat()
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        with self._connect() as db:
            db.execute(
                f"""
                UPDATE drafting_lite_job
                   SET status = 'failed', progress = 0, current_agent = 'coordinator',
                       error_message = '服务重启，未完成任务已终止，请重新生成', updated_at = ?
                 WHERE status IN ({placeholders})
                """,
                (now, *sorted(ACTIVE_STATUSES)),
            )

    def expired(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM drafting_lite_job WHERE expires_at < ?", (_now().isoformat(),)
            ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, job_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM drafting_lite_job WHERE id = ?", (job_id,))
