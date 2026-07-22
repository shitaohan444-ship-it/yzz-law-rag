from __future__ import annotations

import csv
import json
from pathlib import Path

from .storage import StateStore

REPORT_COLUMNS = [
    "relative_path",
    "title",
    "size",
    "sha256",
    "status",
    "doc_id",
    "deduplicated",
    "upload_attempts",
    "ingest_attempts",
    "error_stage",
    "error_message",
    "updated_at",
]


def write_reports(
    store: StateStore, job_id: str, output_dir: Path | None = None
) -> tuple[Path, Path]:
    job = store.get_job(job_id)
    rows = store.list_files(job_id)
    target = output_dir or (store.state_dir / "reports")
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / f"{job_id}.json"
    csv_path = target / f"{job_id}.csv"
    payload = {
        "job": {
            "id": job.id,
            "name": job.name,
            "source_root": job.source_root,
            "category_id": job.category_id,
            "category_name": job.category_name,
            "category_path": list(job.category_path),
            "api_url": job.api_url,
            "created_at": job.created_at,
        },
        "counts": store.counts(job_id),
        "files": [{column: row[column] for column in REPORT_COLUMNS} for row in rows],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows({column: row[column] for column in REPORT_COLUMNS} for row in rows)
    return json_path, csv_path
