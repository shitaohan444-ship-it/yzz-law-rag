from __future__ import annotations

from pathlib import Path

from conftest import make_docx

from law_rag_bulk.runner import ingest_job, retry_job, upload_job
from law_rag_bulk.scanner import scan_docx
from law_rag_bulk.storage import StateStore


class FakeClient:
    def __init__(self) -> None:
        self.upload_calls: list[dict[str, object]] = []
        self.ingest_calls: list[str] = []

    def upload(self, **values: object) -> dict[str, object]:
        self.upload_calls.append(values)
        return {
            "document": {"doc_id": "77", "embedding_status": "pending"},
            "deduplicated": False,
        }

    def ingest(self, doc_id: str) -> dict[str, object]:
        self.ingest_calls.append(doc_id)
        return {"doc_id": int(doc_id), "status": "success", "chunk_count": 2}

    def document_status(self, doc_id: str) -> dict[str, object]:
        return {"doc_id": int(doc_id), "embedding_status": "pending", "chunk_count": 0}


def create_job(store: StateStore, root: Path) -> str:
    return store.create_job(
        name="fixtures",
        source_root=root,
        category_id="2",
        category_name="法律",
        category_path=["法律法规", "法律"],
        api_url="http://platform",
        entries=scan_docx(root),
    )


def test_upload_and_ingest_are_strictly_separate_and_resumable(tmp_path: Path) -> None:
    make_docx(tmp_path / "中文 目录" / "民法典.docx")
    client = FakeClient()
    with StateStore(tmp_path / "state") as store:
        job_id = create_job(store, tmp_path)

        upload_job(store, job_id, client, notify=lambda _: None)  # type: ignore[arg-type]

        assert len(client.upload_calls) == 1
        assert client.upload_calls[0]["relative_path"] == "中文 目录/民法典.docx"
        assert client.ingest_calls == []
        assert store.counts(job_id) == {"uploaded": 1}

        # 已上传项不会再次上传；只有显式调用 ingest_job 才会入库。
        upload_job(store, job_id, client, notify=lambda _: None)  # type: ignore[arg-type]
        assert len(client.upload_calls) == 1
        ingest_job(store, job_id, client, notify=lambda _: None)  # type: ignore[arg-type]
        assert client.ingest_calls == ["77"]
        assert store.counts(job_id) == {"ingested": 1}


def test_source_change_is_blocked_before_upload(tmp_path: Path) -> None:
    path = make_docx(tmp_path / "法规.docx", "v1")
    client = FakeClient()
    with StateStore(tmp_path / "state") as store:
        job_id = create_job(store, tmp_path)
        make_docx(path, "v2 changed")

        upload_job(store, job_id, client, notify=lambda _: None)  # type: ignore[arg-type]

        assert client.upload_calls == []
        assert store.counts(job_id) == {"source_changed": 1}

        assert retry_job(store, job_id, "upload") == 1
        upload_job(store, job_id, client, notify=lambda _: None)  # type: ignore[arg-type]
        assert len(client.upload_calls) == 1
        assert store.counts(job_id) == {"uploaded": 1}
