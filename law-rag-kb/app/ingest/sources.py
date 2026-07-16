"""Multi-source document promotion and atomic full rebuild helpers."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json

from sqlalchemy import delete, func, select, update

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.milvus_client import get_milvus_client
from app.ingest import service
from app.models.tables import (
    kb_document,
    kb_document_image,
    kb_document_source,
    sys_attachment,
)


class SourcePromotionError(RuntimeError):
    """A source append/replacement could not be committed safely."""


@dataclass
class SourcePromotionResult:
    doc_id: int
    source_id: int
    status: str
    source_chunk_count: int
    chunk_count: int
    image_total: int
    upload_timings: dict | None
    ingest_timings: dict | None


@dataclass
class SourcesRebuildResult:
    doc_id: int
    status: str
    chunk_count: int
    image_total: int
    image_kept: int
    image_filtered: int
    vl_status: str
    message: str = ""
    upload_timings: dict | None = None
    ingest_timings: dict | None = None


def promote_staging_source(
    staging_doc_id: int,
    target_doc_id: int,
    source_id: int,
    *,
    mode: str,
    source_title: str | None = None,
) -> SourcePromotionResult:
    if mode not in {"append", "replace"}:
        raise SourcePromotionError("invalid promotion mode")
    staging = service._load_document(staging_doc_id)
    target = service._load_document(target_doc_id)
    source = _load_source(source_id, target_doc_id, include_staging=True)
    if staging is None or target is None or source is None:
        raise service.DocumentNotFoundError("source document not found")
    if staging.get("status") != "staging" or staging.get("embedding_status") != "success":
        raise SourcePromotionError("staging document is not ready")
    if mode == "append" and source["status"] != "staging":
        raise SourcePromotionError("append source is not staging")
    if mode == "replace" and source["status"] != "active":
        raise SourcePromotionError("replace source is not active")

    client = get_milvus_client()
    old_records = service._query_full_chunk_records(target_doc_id, client)
    staging_records = service._query_full_chunk_records(staging_doc_id, client)
    if not staging_records:
        raise SourcePromotionError("staging source has no chunks")
    sources = _load_sources(target_doc_id, include_staging=True)
    primary_id = next((int(item["id"]) for item in sources if item["is_primary"]), None)
    normalized_old = [
        _normalize_existing_record(item, primary_id, sources) for item in old_records
    ]
    if mode == "replace":
        normalized_old = [
            item
            for item in normalized_old
            if int((item.get("meta") or {}).get("source_id") or 0) != source_id
        ]
    title = (source_title or source["source_title"] or "未命名来源").strip()
    file_name = _attachment_name(int(staging["attachment_id"]))
    new_records = [
        _source_record(
            item,
            target_doc_id=target_doc_id,
            source_id=source_id,
            source_title=title,
            source_file_name=file_name,
        )
        for item in sorted(staging_records, key=lambda value: int(value.get("chunk_idx") or 0))
    ]
    combined = _reindex_records(normalized_old + new_records, sources, source_id)
    old_objects: list[tuple[str | None, str | None]] = []
    old_attachment_id = int(source["attachment_id"])
    new_attachment_id = int(staging["attachment_id"])
    try:
        _replace_target_vectors(client, target_doc_id, combined)
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            locked_target = db.execute(
                select(kb_document).where(kb_document.c.id == target_doc_id).with_for_update()
            ).mappings().first()
            locked_staging = db.execute(
                select(kb_document).where(kb_document.c.id == staging_doc_id).with_for_update()
            ).mappings().first()
            locked_source = db.execute(
                select(kb_document_source)
                .where(kb_document_source.c.id == source_id)
                .with_for_update()
            ).mappings().first()
            if not locked_target or not locked_staging or not locked_source:
                raise SourcePromotionError("source state changed")
            if mode == "replace":
                old_attachment = db.execute(
                    select(sys_attachment.c.bucket, sys_attachment.c.object_key).where(
                        sys_attachment.c.id == old_attachment_id
                    )
                ).mappings().first()
                if old_attachment:
                    old_objects.append(
                        (old_attachment["bucket"], old_attachment["object_key"])
                    )
                old_images = db.execute(
                    select(
                        kb_document_image.c.bucket_name,
                        kb_document_image.c.object_key,
                    ).where(
                        kb_document_image.c.document_id == target_doc_id,
                        kb_document_image.c.attachment_id == old_attachment_id,
                    )
                ).mappings().all()
                old_objects.extend(
                    (item["bucket_name"], item["object_key"]) for item in old_images
                )
                db.execute(
                    delete(kb_document_image).where(
                        kb_document_image.c.document_id == target_doc_id,
                        kb_document_image.c.attachment_id == old_attachment_id,
                    )
                )
                db.execute(
                    update(sys_attachment)
                    .where(sys_attachment.c.id == old_attachment_id)
                    .values(status="inactive", deleted_at=now)
                )
            db.execute(
                update(kb_document_image)
                .where(kb_document_image.c.document_id == staging_doc_id)
                .values(document_id=target_doc_id)
            )
            db.execute(
                update(sys_attachment)
                .where(sys_attachment.c.id == new_attachment_id)
                .values(biz_type="knowledge_base", status="active", deleted_at=None)
            )
            source_values = {
                "attachment_id": new_attachment_id,
                "source_title": title,
                "ingest_status": "success",
                "chunk_count": len(new_records),
                "image_total": int(staging.get("image_total") or 0),
                "image_kept": int(staging.get("image_kept") or 0),
                "image_filtered": int(staging.get("image_filtered") or 0),
                "body_markdown": staging.get("body_markdown"),
                "description_summary": staging.get("description_summary"),
                "upload_timings": staging.get("upload_timings"),
                "ingest_timings": staging.get("ingest_timings"),
                "status": "active",
                "deleted_at": None,
                "updated_at": now,
            }
            db.execute(
                update(kb_document_source)
                .where(kb_document_source.c.id == source_id)
                .values(**source_values)
            )
            chunk_counts: dict[int, int] = {}
            for record in combined:
                record_source_id = int((record.get("meta") or {}).get("source_id") or 0)
                if record_source_id:
                    chunk_counts[record_source_id] = chunk_counts.get(record_source_id, 0) + 1
            for record_source_id, chunk_count in chunk_counts.items():
                db.execute(
                    update(kb_document_source)
                    .where(
                        kb_document_source.c.id == record_source_id,
                        kb_document_source.c.document_id == target_doc_id,
                        kb_document_source.c.deleted_at.is_(None),
                    )
                    .values(chunk_count=chunk_count, updated_at=now)
                )
            if bool(source["is_primary"]):
                db.execute(
                    update(kb_document)
                    .where(kb_document.c.id == target_doc_id)
                    .values(
                        attachment_id=new_attachment_id,
                        body_markdown=staging.get("body_markdown"),
                        description_summary=staging.get("description_summary"),
                    )
                )
            totals = db.execute(
                select(
                    func.coalesce(func.sum(kb_document_source.c.image_total), 0),
                    func.coalesce(func.sum(kb_document_source.c.image_kept), 0),
                    func.coalesce(func.sum(kb_document_source.c.image_filtered), 0),
                ).where(
                    kb_document_source.c.document_id == target_doc_id,
                    kb_document_source.c.deleted_at.is_(None),
                    kb_document_source.c.status.in_(["active", "staging"]),
                )
            ).one()
            db.execute(
                update(kb_document)
                .where(kb_document.c.id == target_doc_id)
                .values(
                    embedding_status="success",
                    image_total=int(totals[0] or 0),
                    image_kept=int(totals[1] or 0),
                    image_filtered=int(totals[2] or 0),
                    updated_at=now,
                )
            )
            db.execute(
                update(kb_document)
                .where(kb_document.c.id == staging_doc_id)
                .values(status="replaced", deleted_at=now, updated_at=now)
            )
            db.commit()
    except Exception as exc:
        _restore_vectors(client, target_doc_id, old_records)
        if isinstance(exc, (SourcePromotionError, service.DocumentNotFoundError)):
            raise
        raise SourcePromotionError("source promotion failed") from exc

    _delete_staging_vectors(client, staging_doc_id)
    for bucket, object_key in old_objects:
        service._remove_object_safely(bucket, object_key)
    return SourcePromotionResult(
        doc_id=target_doc_id,
        source_id=source_id,
        status="success",
        source_chunk_count=len(new_records),
        chunk_count=len(combined),
        image_total=sum(int(item.get("image_total") or 0) for item in _load_sources(target_doc_id)),
        upload_timings=staging.get("upload_timings"),
        ingest_timings=staging.get("ingest_timings"),
    )


def cleanup_source_staging(source_id: int) -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.execute(
            update(kb_document_source)
            .where(
                kb_document_source.c.id == source_id,
                kb_document_source.c.status == "staging",
            )
            .values(status="cancelled", deleted_at=now, updated_at=now)
        )
        db.commit()


def rebuild_from_staging_sources(
    target_doc_id: int, items: list[tuple[int, int]]
) -> SourcesRebuildResult:
    """Replace all source chunks only after every staging source is ready."""
    target = service._load_document(target_doc_id)
    sources = _load_sources(target_doc_id)
    if target is None or not sources:
        raise service.DocumentNotFoundError("kb_document not found")
    expected = {int(item["id"]) for item in sources}
    supplied = {source_id for source_id, _ in items}
    if expected != supplied:
        raise SourcePromotionError("rebuild sources do not match active sources")
    source_map = {int(item["id"]): item for item in sources}
    client = get_milvus_client()
    old_records = service._query_full_chunk_records(target_doc_id, client)
    staging_rows: list[tuple[int, int, dict, list[dict]]] = []
    all_records: list[dict] = []
    for source_id, staging_doc_id in items:
        staging = service._load_document(staging_doc_id)
        if (
            staging is None
            or staging.get("status") != "staging"
            or staging.get("embedding_status") != "success"
        ):
            raise SourcePromotionError("a rebuild staging source is not ready")
        records = service._query_full_chunk_records(staging_doc_id, client)
        if not records:
            raise SourcePromotionError("a rebuild staging source has no chunks")
        source = source_map[source_id]
        file_name = _attachment_name(int(source["attachment_id"]))
        promoted = [
            _source_record(
                record,
                target_doc_id=target_doc_id,
                source_id=source_id,
                source_title=source["source_title"],
                source_file_name=file_name,
            )
            for record in sorted(records, key=lambda value: int(value.get("chunk_idx") or 0))
        ]
        staging_rows.append((source_id, staging_doc_id, staging, promoted))
        all_records.extend(promoted)
    combined = _reindex_records(all_records, sources, 0)
    old_image_objects: list[tuple[str | None, str | None]] = []
    try:
        _replace_target_vectors(client, target_doc_id, combined)
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            locked_target = db.execute(
                select(kb_document).where(kb_document.c.id == target_doc_id).with_for_update()
            ).mappings().first()
            if not locked_target or locked_target["status"] != "active":
                raise SourcePromotionError("target document state changed")
            old_images = db.execute(
                select(
                    kb_document_image.c.bucket_name,
                    kb_document_image.c.object_key,
                ).where(kb_document_image.c.document_id == target_doc_id)
            ).mappings().all()
            old_image_objects.extend(
                (item["bucket_name"], item["object_key"]) for item in old_images
            )
            db.execute(
                delete(kb_document_image).where(
                    kb_document_image.c.document_id == target_doc_id
                )
            )
            primary_staging: dict | None = None
            for source_id, staging_doc_id, staging, promoted in staging_rows:
                source = source_map[source_id]
                db.execute(
                    update(kb_document_image)
                    .where(kb_document_image.c.document_id == staging_doc_id)
                    .values(document_id=target_doc_id)
                )
                db.execute(
                    update(kb_document_source)
                    .where(kb_document_source.c.id == source_id)
                    .values(
                        ingest_status="success",
                        chunk_count=len(promoted),
                        image_total=int(staging.get("image_total") or 0),
                        image_kept=int(staging.get("image_kept") or 0),
                        image_filtered=int(staging.get("image_filtered") or 0),
                        body_markdown=staging.get("body_markdown"),
                        description_summary=staging.get("description_summary"),
                        ingest_timings=staging.get("ingest_timings"),
                        updated_at=now,
                    )
                )
                db.execute(
                    update(kb_document)
                    .where(kb_document.c.id == staging_doc_id)
                    .values(status="replaced", deleted_at=now, updated_at=now)
                )
                if source["is_primary"]:
                    primary_staging = staging
            image_total = sum(int(item[2].get("image_total") or 0) for item in staging_rows)
            image_kept = sum(int(item[2].get("image_kept") or 0) for item in staging_rows)
            image_filtered = sum(int(item[2].get("image_filtered") or 0) for item in staging_rows)
            db.execute(
                update(kb_document)
                .where(kb_document.c.id == target_doc_id)
                .values(
                    embedding_status="success",
                    image_total=image_total,
                    image_kept=image_kept,
                    image_filtered=image_filtered,
                    body_markdown=(primary_staging or {}).get("body_markdown"),
                    description_summary=(primary_staging or {}).get("description_summary"),
                    ingest_timings=(primary_staging or {}).get("ingest_timings"),
                    updated_at=now,
                )
            )
            db.commit()
    except Exception as exc:
        _restore_vectors(client, target_doc_id, old_records)
        if isinstance(exc, (SourcePromotionError, service.DocumentNotFoundError)):
            raise
        raise SourcePromotionError("full source rebuild failed") from exc
    for _, staging_doc_id, _, _ in staging_rows:
        _delete_staging_vectors(client, staging_doc_id)
    for bucket, object_key in old_image_objects:
        service._remove_object_safely(bucket, object_key)
    return SourcesRebuildResult(
        doc_id=target_doc_id,
        status="success",
        chunk_count=len(combined),
        image_total=sum(int(item[2].get("image_total") or 0) for item in staging_rows),
        image_kept=sum(int(item[2].get("image_kept") or 0) for item in staging_rows),
        image_filtered=sum(int(item[2].get("image_filtered") or 0) for item in staging_rows),
        vl_status="success",
        ingest_timings=(next((item[2] for item in staging_rows if source_map[item[0]]["is_primary"]), {}) or {}).get("ingest_timings"),
    )


def _load_source(source_id: int, document_id: int, *, include_staging: bool = False):
    allowed = ["active", "staging"] if include_staging else ["active"]
    with SessionLocal() as db:
        return db.execute(
            select(kb_document_source).where(
                kb_document_source.c.id == source_id,
                kb_document_source.c.document_id == document_id,
                kb_document_source.c.deleted_at.is_(None),
                kb_document_source.c.status.in_(allowed),
            )
        ).mappings().first()


def _load_sources(document_id: int, *, include_staging: bool = False) -> list:
    allowed = ["active", "staging"] if include_staging else ["active"]
    with SessionLocal() as db:
        return list(
            db.execute(
                select(kb_document_source)
                .where(
                    kb_document_source.c.document_id == document_id,
                    kb_document_source.c.deleted_at.is_(None),
                    kb_document_source.c.status.in_(allowed),
                )
                .order_by(kb_document_source.c.sort_order, kb_document_source.c.id)
            ).mappings().all()
        )


def _attachment_name(attachment_id: int) -> str:
    with SessionLocal() as db:
        row = db.execute(
            select(sys_attachment.c.file_name).where(sys_attachment.c.id == attachment_id)
        ).first()
    return str(row[0] if row else "")


def _normalize_existing_record(record: dict, primary_id: int | None, sources: list) -> dict:
    item = dict(record)
    meta = dict(item.get("meta") or {})
    source_id = int(meta.get("source_id") or primary_id or 0)
    source = next((value for value in sources if int(value["id"]) == source_id), None)
    meta.update(
        {
            "source_id": source_id or None,
            "source_title": meta.get("source_title") or (source["source_title"] if source else None),
            "source_file_name": meta.get("source_file_name")
            or (_attachment_name(int(source["attachment_id"])) if source else None),
            "source_chunk_idx": int(meta.get("source_chunk_idx") or item.get("chunk_idx") or 0),
        }
    )
    item["meta"] = meta
    return item


def _source_record(
    record: dict,
    *,
    target_doc_id: int,
    source_id: int,
    source_title: str,
    source_file_name: str,
) -> dict:
    local_idx = int(record.get("chunk_idx") or 0)
    old_id = str(record.get("id") or "")
    kind = "i" if ":i:" in old_id else "m"
    suffix = old_id.split(":i:", 1)[1] if kind == "i" else f"{local_idx:04d}"
    meta = dict(record.get("meta") or {})
    meta.update(
        {
            "source_id": source_id,
            "source_title": source_title,
            "source_file_name": source_file_name,
            "source_chunk_idx": local_idx,
            "doc_title": meta.get("doc_title"),
        }
    )
    return {
        "id": f"{target_doc_id}:s:{source_id}:{kind}:{suffix}",
        "doc_id": target_doc_id,
        "chunk_idx": local_idx,
        "source": record.get("source") or "",
        "chunk_text": record.get("chunk_text") or "",
        "dense": record.get("dense"),
        "sparse": record.get("sparse"),
        "meta": meta,
    }


def _reindex_records(records: list[dict], sources: list, promoted_source_id: int) -> list[dict]:
    order = {int(item["id"]): int(item["sort_order"] or 0) for item in sources}
    order.setdefault(promoted_source_id, max(order.values(), default=-1) + 1)
    values = sorted(
        records,
        key=lambda item: (
            order.get(int((item.get("meta") or {}).get("source_id") or 0), 2**31),
            int((item.get("meta") or {}).get("source_chunk_idx") or 0),
            str(item.get("id") or ""),
        ),
    )
    for index, item in enumerate(values):
        item["chunk_idx"] = index
    return values


def _replace_target_vectors(client, target_doc_id: int, records: list[dict]) -> None:
    client.upsert(settings.milvus_collection, data=records)
    ids = json.dumps([item["id"] for item in records], ensure_ascii=False)
    client.delete(
        settings.milvus_collection,
        filter=f"doc_id == {target_doc_id} and id not in {ids}",
    )


def _restore_vectors(client, target_doc_id: int, records: list[dict]) -> None:
    try:
        client.delete(settings.milvus_collection, filter=f"doc_id == {target_doc_id}")
        if records:
            client.upsert(settings.milvus_collection, data=records)
    except Exception:
        pass


def _delete_staging_vectors(client, staging_doc_id: int) -> None:
    try:
        client.delete(settings.milvus_collection, filter=f"doc_id == {staging_doc_id}")
    except Exception:
        pass
