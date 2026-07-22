from __future__ import annotations

from pathlib import Path

from law_rag_bulk.scanner import ScanEntry
from law_rag_bulk.storage import StateStore


def entry(status: str = "ready") -> ScanEntry:
    return ScanEntry(
        relative_path="法规/民法典.docx",
        absolute_path="C:/fixtures/法规/民法典.docx",
        title="民法典",
        size=123,
        mtime_ns=456,
        sha256="a" * 64 if status == "ready" else None,
        status=status,
        error_message=None,
    )


def test_persists_locked_category_and_recovers_interrupted_upload(tmp_path: Path) -> None:
    with StateStore(tmp_path) as store:
        job_id = store.create_job(
            name="法规任务",
            source_root=tmp_path,
            category_id="42",
            category_name="民事法律",
            category_path=["法律法规", "民事法律"],
            api_url="http://127.0.0.1:3000",
            entries=[entry()],
        )
        row = store.list_files(job_id)[0]
        store.update_file(row["id"], status="uploading")

    with StateStore(tmp_path) as reopened:
        job = reopened.get_job(job_id)
        assert job.category_id == "42"
        assert job.category_path == ("法律法规", "民事法律")
        assert reopened.list_files(job_id)[0]["status"] == "ready"


def test_retry_resets_only_the_selected_failure_stage(tmp_path: Path) -> None:
    with StateStore(tmp_path) as store:
        job_id = store.create_job(
            name="retry",
            source_root=tmp_path,
            category_id="2",
            category_name="法律",
            category_path=["法律"],
            api_url="http://api",
            entries=[entry()],
        )
        file_id = store.list_files(job_id)[0]["id"]
        store.update_file(file_id, status="upload_failed", error_message="network")
        assert store.retry(job_id, "ingest") == 0
        assert store.retry(job_id, "upload") == 1
        assert store.list_files(job_id)[0]["status"] == "ready"
