from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .client import ApiConflict, ApiTimeout, PlatformClient
from .scanner import sha256_file, validate_docx
from .storage import StateStore


def retry_job(store: StateStore, job_id: str, stage: str) -> int:
    """重置失败状态；源文件变化项在用户显式 retry 时重新建立校验基线。"""
    reset = store.retry(job_id, stage)
    if stage != "upload":
        return reset
    for row in store.list_files(job_id, ["source_changed"]):
        path = Path(row["absolute_path"])
        try:
            validate_docx(path)
            stat = path.stat()
            digest = sha256_file(path)
        except (OSError, ValueError) as exc:
            store.update_file(
                row["id"], error_stage="upload", error_message=f"源文件仍不可用: {exc}"
            )
            continue
        store.update_file(
            row["id"],
            status="ready",
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            sha256=digest,
            error_stage=None,
            error_message=None,
        )
        reset += 1
    return reset


def upload_job(
    store: StateStore,
    job_id: str,
    client: PlatformClient,
    *,
    limit: int | None = None,
    notify: Callable[[str], None] = print,
) -> dict[str, int]:
    job = store.get_job(job_id)
    rows = store.list_files(job_id, ["ready"])
    if limit is not None:
        rows = rows[: max(0, limit)]
    for row in rows:
        file_id = row["id"]
        attempts = row["upload_attempts"] + 1
        store.update_file(
            file_id,
            status="uploading",
            upload_attempts=attempts,
            error_stage=None,
            error_message=None,
        )
        path = Path(row["absolute_path"])
        try:
            stat = path.stat()
            validate_docx(path)
            current_hash = sha256_file(path)
            if stat.st_size != row["size"] or current_hash != row["sha256"]:
                store.update_file(
                    file_id,
                    status="source_changed",
                    error_stage="upload",
                    error_message="源文件在任务创建后发生变化，请核对后重试",
                )
                notify(f"SOURCE_CHANGED {row['relative_path']}")
                continue
            payload = client.upload(
                path=path,
                title=row["title"],
                category_id=job.category_id,
                relative_path=row["relative_path"],
            )
            document = payload.get("document", {})
            doc_id = str(document.get("doc_id", ""))
            if not doc_id:
                raise RuntimeError("上传接口没有返回 doc_id")
            deduplicated = bool(payload.get("deduplicated"))
            already_ingested = document.get("embedding_status") == "success"
            status = (
                "ingested" if already_ingested else ("deduplicated" if deduplicated else "uploaded")
            )
            # 待入库的去重文档仍需进入 uploaded 状态；deduplicated 由独立字段记录。
            if status == "deduplicated":
                status = "uploaded"
            store.update_file(
                file_id,
                status=status,
                doc_id=doc_id,
                deduplicated=1 if deduplicated else 0,
                error_stage=None,
                error_message=None,
            )
            notify(f"{status.upper()} {row['relative_path']} -> doc_id={doc_id}")
        except ApiConflict as exc:
            store.update_file(
                file_id, status="conflict", error_stage="upload", error_message=str(exc)
            )
            notify(f"CONFLICT {row['relative_path']}: {exc}")
        except Exception as exc:  # 每个文件隔离失败，任务继续并保留错误供 retry/report
            store.update_file(
                file_id, status="upload_failed", error_stage="upload", error_message=str(exc)
            )
            notify(f"UPLOAD_FAILED {row['relative_path']}: {exc}")
    return store.counts(job_id)


def ingest_job(
    store: StateStore,
    job_id: str,
    client: PlatformClient,
    *,
    limit: int | None = None,
    notify: Callable[[str], None] = print,
) -> dict[str, int]:
    rows = store.list_files(job_id, ["uploaded"])
    if limit is not None:
        rows = rows[: max(0, limit)]
    for row in rows:
        file_id = row["id"]
        doc_id = row["doc_id"]
        attempts = row["ingest_attempts"] + 1
        store.update_file(
            file_id,
            status="ingesting",
            ingest_attempts=attempts,
            error_stage=None,
            error_message=None,
        )
        try:
            payload = client.ingest(doc_id)
            if payload.get("status") != "success":
                raise RuntimeError(f"RAG 返回非成功状态: {payload.get('status')}")
            store.update_file(file_id, status="ingested", error_stage=None, error_message=None)
            notify(f"INGESTED {row['relative_path']} -> doc_id={doc_id}")
        except ApiTimeout as exc:
            try:
                status = client.document_status(doc_id)
            except Exception as status_exc:
                store.update_file(
                    file_id,
                    status="ingest_failed",
                    error_stage="ingest",
                    error_message=f"{exc}; 状态复核失败: {status_exc}",
                )
            else:
                if status.get("embedding_status") == "success":
                    store.update_file(
                        file_id, status="ingested", error_stage=None, error_message=None
                    )
                    notify(f"INGESTED_AFTER_TIMEOUT {row['relative_path']} -> doc_id={doc_id}")
                else:
                    store.update_file(
                        file_id,
                        status="ingest_failed",
                        error_stage="ingest",
                        error_message=str(exc),
                    )
        except Exception as exc:
            store.update_file(
                file_id, status="ingest_failed", error_stage="ingest", error_message=str(exc)
            )
            notify(f"INGEST_FAILED {row['relative_path']}: {exc}")
    return store.counts(job_id)
