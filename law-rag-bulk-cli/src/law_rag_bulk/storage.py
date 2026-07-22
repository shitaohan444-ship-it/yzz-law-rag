from __future__ import annotations

import json
import os
import sqlite3
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .scanner import ScanEntry

DEFAULT_STATE_DIR = Path(os.environ.get("LAW_RAG_BULK_DATA", r"D:\law-rag-bulk-data"))


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Job:
    id: str
    name: str
    source_root: str
    category_id: str
    category_name: str
    category_path: tuple[str, ...]
    api_url: str
    created_at: str


class StateStore:
    def __init__(self, state_dir: Path = DEFAULT_STATE_DIR):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / "bulk-import.sqlite3"
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._initialize()
        self.recover_incomplete()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> StateStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              source_root TEXT NOT NULL,
              category_id TEXT NOT NULL,
              category_name TEXT NOT NULL,
              category_path_json TEXT NOT NULL,
              api_url TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS files (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
              relative_path TEXT NOT NULL,
              absolute_path TEXT NOT NULL,
              title TEXT NOT NULL,
              size INTEGER NOT NULL,
              mtime_ns INTEGER NOT NULL,
              sha256 TEXT,
              status TEXT NOT NULL,
              doc_id TEXT,
              deduplicated INTEGER NOT NULL DEFAULT 0,
              upload_attempts INTEGER NOT NULL DEFAULT 0,
              ingest_attempts INTEGER NOT NULL DEFAULT 0,
              error_stage TEXT,
              error_message TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(job_id, relative_path)
            );
            CREATE INDEX IF NOT EXISTS idx_files_job_status ON files(job_id, status);
            """
        )
        self.connection.commit()

    def recover_incomplete(self) -> None:
        now = utc_now()
        with self.connection:
            self.connection.execute(
                "UPDATE files SET status='ready', error_stage='upload', "
                "error_message='上次上传被中断，已恢复待上传', updated_at=? "
                "WHERE status='uploading'",
                (now,),
            )
            self.connection.execute(
                "UPDATE files SET status='uploaded', error_stage='ingest', "
                "error_message='上次入库被中断，已恢复待入库', updated_at=? "
                "WHERE status='ingesting'",
                (now,),
            )

    def create_job(
        self,
        *,
        name: str,
        source_root: Path,
        category_id: str,
        category_name: str,
        category_path: list[str],
        api_url: str,
        entries: Iterable[ScanEntry],
    ) -> str:
        job_id = str(uuid.uuid4())
        now = utc_now()
        rows = list(entries)
        with self.connection:
            self.connection.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    name,
                    str(source_root.resolve()),
                    category_id,
                    category_name,
                    json.dumps(category_path, ensure_ascii=False),
                    api_url.rstrip("/"),
                    now,
                    now,
                ),
            )
            self.connection.executemany(
                """INSERT INTO files (
                  job_id, relative_path, absolute_path, title, size, mtime_ns, sha256,
                  status, error_stage, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        job_id,
                        entry.relative_path,
                        entry.absolute_path,
                        entry.title,
                        entry.size,
                        entry.mtime_ns,
                        entry.sha256,
                        entry.status,
                        "scan" if entry.status == "invalid" else None,
                        entry.error_message,
                        now,
                        now,
                    )
                    for entry in rows
                ],
            )
        return job_id

    def get_job(self, job_id: str) -> Job:
        row = self.connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"任务不存在: {job_id}")
        return Job(
            id=row["id"],
            name=row["name"],
            source_root=row["source_root"],
            category_id=row["category_id"],
            category_name=row["category_name"],
            category_path=tuple(json.loads(row["category_path_json"])),
            api_url=row["api_url"],
            created_at=row["created_at"],
        )

    def list_files(self, job_id: str, statuses: Iterable[str] | None = None) -> list[sqlite3.Row]:
        params: list[object] = [job_id]
        sql = "SELECT * FROM files WHERE job_id=?"
        if statuses:
            values = list(statuses)
            sql += f" AND status IN ({','.join('?' for _ in values)})"
            params.extend(values)
        sql += " ORDER BY relative_path COLLATE NOCASE"
        return list(self.connection.execute(sql, params))

    def update_file(self, file_id: int, **values: object) -> None:
        if not values:
            return
        allowed = {
            "status",
            "doc_id",
            "deduplicated",
            "upload_attempts",
            "ingest_attempts",
            "error_stage",
            "error_message",
            "size",
            "mtime_ns",
            "sha256",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"不允许更新字段: {sorted(unknown)}")
        values["updated_at"] = utc_now()
        assignments = ", ".join(f"{key}=?" for key in values)
        with self.connection:
            self.connection.execute(
                f"UPDATE files SET {assignments} WHERE id=?",
                [*values.values(), file_id],
            )

    def counts(self, job_id: str) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT status, COUNT(*) AS count FROM files WHERE job_id=? GROUP BY status",
            (job_id,),
        )
        return {row["status"]: row["count"] for row in rows}

    def retry(self, job_id: str, stage: str) -> int:
        now = utc_now()
        if stage == "upload":
            source, target = ("upload_failed",), "ready"
        elif stage == "ingest":
            source, target = ("ingest_failed",), "uploaded"
        else:
            raise ValueError("stage 必须是 upload 或 ingest")
        placeholders = ",".join("?" for _ in source)
        with self.connection:
            cursor = self.connection.execute(
                f"UPDATE files SET status=?, error_stage=NULL, error_message=NULL, updated_at=? "
                f"WHERE job_id=? AND status IN ({placeholders})",
                (target, now, job_id, *source),
            )
        return cursor.rowcount
