"""入库链：源文件 → Markdown → draft 切片 → VL 回填 → 最终切片 → 向量化。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.constants import EmbeddingStatus
from app.core.database import SessionLocal
from app.core.milvus_client import ensure_collection, get_milvus_client
from app.core.storage import download as minio_download
from app.core.minio_client import get_minio_client
from app.core.storage import file_exists as minio_file_exists
from app.core.storage import presigned_url as minio_presigned_url
from app.core.storage import upload_derived
from app.ingest import chunker, cleaner, embedding, image_filter, markdown_builder, parser, vl
from app.ingest.document import ContentNode, ImageAnalysis, ParsedDocument
from app.ingest.parser import UnsupportedFileTypeError
from app.ingest.timing import PipelineTimer
from app.models.tables import (
    kb_document,
    kb_document_image,
    kb_document_source,
    sys_attachment,
)
from app.rag import describe, markdown as markdown_utils
from app.rag.category_resolver import resolve_document_categories

_CHUNK_TEXT_MAX = 65535
_INGEST_FAILED_CODE = "RAG_INGEST_FAILED"
_UNSUPPORTED_FILE_CODE = "RAG_UNSUPPORTED_FILE_TYPE"
logger = logging.getLogger("uvicorn.error")


class DocumentNotFoundError(LookupError):
    """Requested kb_document does not exist."""


class DocumentChunksUnavailableError(RuntimeError):
    """Milvus could not provide a valid chunk page."""


class DocumentPromotionError(RuntimeError):
    """A staging document could not safely replace its target."""


@dataclass
class IngestResult:
    doc_id: int
    status: str
    chunk_count: int = 0
    image_total: int = 0
    image_kept: int = 0
    image_filtered: int = 0
    vl_status: str = "not_processed"
    message: str = ""
    error_code: str | None = None
    upload_timings: dict | None = None
    ingest_timings: dict | None = None


@dataclass
class DocumentStatus:
    doc_id: int
    embedding_status: str
    chunk_count: int
    doc_title: str | None = None
    vl_status: str = "not_processed"
    image_total: int = 0
    image_kept: int = 0
    image_filtered: int = 0
    vl_processed_at: datetime | None = None
    error_code: str | None = None
    upload_timings: dict | None = None
    ingest_timings: dict | None = None


@dataclass
class DocumentMarkdown:
    """GET /documents/{id}/markdown 渲染结果。"""
    doc_id: int
    doc_title: str | None
    description_summary: str | None
    image_count: int
    markdown: str
    source_count: int = 1
    source_id: int | None = None


@dataclass
class DocumentChunk:
    chunk_id: str
    chunk_idx: int
    text: str
    char_count: int
    source: str | None
    article_no: str | None
    chapter: str | None
    content_type: str | None
    image_id: int | None
    page_no: int | None
    image_category: str | None
    source_id: int | None = None
    source_title: str | None = None
    source_file_name: str | None = None
    source_chunk_idx: int | None = None


@dataclass
class DocumentChunks:
    doc_id: int
    doc_title: str | None
    total: int
    page: int
    page_size: int
    items: list[DocumentChunk]


@dataclass(frozen=True)
class _VectorChunk:
    stable_id: str
    idx: int
    text: str
    content_type: str
    article_no: str | None = None
    chapter: str | None = None
    image_id: int | None = None
    page_no: int | None = None
    image_category: str | None = None


def ingest_document(
    doc_id: int,
    *,
    force: bool = False,
    generate_description: bool = True,
    analyze_images: bool = True,
) -> IngestResult:
    """同步入库一个文档；可按单次任务关闭付费摘要和图片分析。"""
    row = _load_document(doc_id)
    if row is None:
        raise DocumentNotFoundError("kb_document not found")

    attachment_id = row["attachment_id"]
    if row["embedding_status"] == EmbeddingStatus.SUCCESS and not force:
        return IngestResult(
            doc_id,
            EmbeddingStatus.SKIPPED,
            vl_status=row.get("vl_status") or "not_processed",
            image_total=row.get("image_total") or 0,
            image_kept=row.get("image_kept") or 0,
            image_filtered=row.get("image_filtered") or 0,
            message="already ingested (use force=true to redo)",
            upload_timings=row.get("upload_timings"),
            ingest_timings=row.get("ingest_timings"),
        )

    timer = PipelineTimer()
    _set_status(
        doc_id,
        EmbeddingStatus.PROCESSING,
        attachment_id=attachment_id,
        vl_status="processing",
    )
    analyses: list[ImageAnalysis] = []
    try:
        with timer.stage("milvus_prepare", "Milvus collection 准备"):
            ensure_collection()
        with timer.stage("source_parse", "MinIO 原件下载与文件解析"):
            parsed, source_hash = _resolve_document(row, attachment_id)
        with timer.stage("clean_image_dedup", "文本清理与图片去重"):
            cleaned = cleaner.clean(parsed)
            unique_images = image_filter.deduplicate(cleaned.images)
        title = row["doc_title"] or "未命名文档"

        if settings.kb_markdown_pipeline:
            with timer.stage("markdown_draft", "初始 Markdown 和 draft Chunk"):
                image_ids, stored_hashes = _store_pending_images(
                    doc_id,
                    attachment_id=attachment_id,
                    source_hash=source_hash,
                    images=unique_images,
                )
                initial_markdown = markdown_builder.build_initial_markdown(
                    title, cleaned, image_ids
                )
                draft_chunks = markdown_builder.split_markdown_draft(
                    initial_markdown,
                    chunk_size=settings.chunk_size,
                    overlap=settings.chunk_overlap,
                )
                contexts = markdown_builder.image_contexts(draft_chunks)
            if unique_images and analyze_images:
                with timer.stage("vl_analysis", "图片 VL 分析"):
                    analyses = _analyze_images_after_draft(
                        unique_images,
                        doc_title=title,
                        image_ids=image_ids,
                        contexts=contexts,
                        stored_hashes=stored_hashes,
                    )
            else:
                timer.skip("vl_analysis", "图片 VL 分析")
                if unique_images:
                    analyses = _cloud_disabled_image_analyses(unique_images)
            _update_image_analyses(doc_id, analyses)
            vl_status = _derive_vl_status(analyses)
            counts = _image_counts(analyses)
            _set_vl_summary(doc_id, vl_status=vl_status, **counts)

            if generate_description:
                with timer.stage("summary_generation", "文档摘要生成"):
                    description_summary = _generate_doc_description(title, cleaned, analyses)
            else:
                timer.skip("summary_generation", "文档摘要生成")
                description_summary = None
            with timer.stage("final_chunking", "最终 Markdown 与 Chunk 构建"):
                analyses_by_id = {
                    image_ids[item.asset.sha256]: item
                    for item in analyses
                    if item.asset.sha256 in image_ids
                }
                enriched_drafts = markdown_builder.enrich_drafts(
                    draft_chunks, analyses_by_id
                )
                final_chunks = markdown_builder.finalize_chunks(
                    enriched_drafts,
                    description_summary=description_summary,
                    doc_title=title,
                    chunk_size=settings.chunk_size,
                    overlap=settings.chunk_overlap,
                )
                body_markdown = markdown_builder.enrich_markdown(
                    initial_markdown,
                    analyses_by_id,
                    description_summary=description_summary,
                )
                vector_chunks = _build_markdown_vector_chunks(
                    doc_id, final_chunks, analyses_by_id
                )
        else:
            timer.skip("markdown_draft", "初始 Markdown 和 draft Chunk")
            if unique_images and analyze_images:
                with timer.stage("vl_analysis", "图片 VL 分析"):
                    analyses = _analyze_images(unique_images, doc_title=title)
            else:
                timer.skip("vl_analysis", "图片 VL 分析")
                if unique_images:
                    analyses = _cloud_disabled_image_analyses(unique_images)
            with timer.stage("final_chunking", "最终 Markdown 与 Chunk 构建"):
                image_ids = _store_image_analyses(
                    doc_id,
                    attachment_id=attachment_id,
                    source_hash=source_hash,
                    analyses=analyses,
                )
                vector_chunks = _build_vector_chunks(doc_id, cleaned, analyses, image_ids)
            vl_status = _derive_vl_status(analyses)
            counts = _image_counts(analyses)
            _set_vl_summary(doc_id, vl_status=vl_status, **counts)
            if generate_description:
                with timer.stage("summary_generation", "文档摘要生成"):
                    description_summary = _generate_doc_description(title, cleaned, analyses)
            else:
                timer.skip("summary_generation", "文档摘要生成")
                description_summary = None
            body_markdown = None

        if not vector_chunks:
            raise RuntimeError("empty content after text and image processing")
        with timer.stage("embedding", "BGE-M3 Embedding"):
            dense, sparse = embedding.encode_batch([item.text for item in vector_chunks])
            records = _build_records(doc_id, row, vector_chunks, dense, sparse)
        with timer.stage("milvus_write", "Milvus 写入与旧 Chunk 清理"):
            client = get_milvus_client()
            # 先 upsert 新数据，再删除不在新 ID 集合中的旧记录，避免失败造成空窗。
            client.upsert(settings.milvus_collection, data=records)
            new_ids = json.dumps([record["id"] for record in records], ensure_ascii=False)
            client.delete(
                settings.milvus_collection,
                filter=f"doc_id == {doc_id} and id not in {new_ids}",
            )
    except UnsupportedFileTypeError:
        logger.exception(
            "document ingest failed doc_id=%s error_code=%s",
            doc_id,
            _UNSUPPORTED_FILE_CODE,
        )
        with timer.stage("status_writeback", "状态回写"):
            _set_status(
                doc_id,
                EmbeddingStatus.FAILED,
                attachment_id=attachment_id,
                error_code=_UNSUPPORTED_FILE_CODE,
                vl_status="failed" if analyses else "not_processed",
            )
        report = timer.report("failed")
        _set_ingest_timings(doc_id, report)
        return IngestResult(
            doc_id,
            EmbeddingStatus.FAILED,
            message="不支持的文档格式",
            error_code=_UNSUPPORTED_FILE_CODE,
            upload_timings=row.get("upload_timings"), ingest_timings=report
        )
    except Exception as exc:
        logger.exception(
            "document ingest failed doc_id=%s error_code=%s",
            doc_id,
            _INGEST_FAILED_CODE,
        )
        summary = _image_counts(analyses)
        derived_status = _derive_vl_status(analyses) if analyses else "failed"
        with timer.stage("status_writeback", "状态回写"):
            _set_status(
                doc_id,
                EmbeddingStatus.FAILED,
                attachment_id=attachment_id,
                error_code=_INGEST_FAILED_CODE,
                vl_status=derived_status,
                **summary,
            )
        report = timer.report("failed")
        _set_ingest_timings(doc_id, report)
        return IngestResult(
            doc_id,
            EmbeddingStatus.FAILED,
            vl_status=derived_status,
            message="文档处理失败，请检查文件后重试",
            error_code=_INGEST_FAILED_CODE,
            upload_timings=row.get("upload_timings"),
            ingest_timings=report,
            **summary,
        )

    counts = _image_counts(analyses)
    final_vl_status = _derive_vl_status(analyses)
    with timer.stage("status_writeback", "状态回写"):
        _set_status(
            doc_id,
            EmbeddingStatus.SUCCESS,
            attachment_id=attachment_id,
            vl_status=final_vl_status,
            description_summary=description_summary,
            body_markdown=body_markdown,
            **counts,
        )
    report = timer.report("success")
    _set_ingest_timings(doc_id, report)
    _sync_primary_source(doc_id, len(vector_chunks), report)
    return IngestResult(
        doc_id,
        EmbeddingStatus.SUCCESS,
        chunk_count=len(vector_chunks),
        vl_status=final_vl_status,
        upload_timings=row.get("upload_timings"),
        ingest_timings=report,
        **counts,
    )


def get_document_status(doc_id: int) -> DocumentStatus | None:
    with SessionLocal() as db:
        row = db.execute(
            select(
                kb_document.c.id,
                kb_document.c.doc_title,
                kb_document.c.embedding_status,
                kb_document.c.vl_status,
                kb_document.c.image_total,
                kb_document.c.image_kept,
                kb_document.c.image_filtered,
                kb_document.c.vl_processed_at,
                kb_document.c.remark,
                kb_document.c.upload_timings,
                kb_document.c.ingest_timings,
            ).where(kb_document.c.id == doc_id)
        ).mappings().first()
    if row is None:
        return None
    return DocumentStatus(
        doc_id=doc_id,
        doc_title=row["doc_title"],
        embedding_status=row["embedding_status"],
        chunk_count=_count_chunks(doc_id),
        vl_status=row["vl_status"] or "not_processed",
        image_total=row["image_total"] or 0,
        image_kept=row["image_kept"] or 0,
        image_filtered=row["image_filtered"] or 0,
        vl_processed_at=row["vl_processed_at"],
        error_code=(
            row["remark"]
            if row["embedding_status"] in {EmbeddingStatus.FAILED, EmbeddingStatus.SKIPPED}
            and str(row["remark"] or "").startswith("RAG_")
            else None
        ),
        upload_timings=row["upload_timings"],
        ingest_timings=row["ingest_timings"],
    )


def get_document_chunks(
    doc_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
    source_id: int | None = None,
) -> DocumentChunks | None:
    """Return one ordered chunk page without exposing vector fields."""
    row = _load_document(doc_id)
    if row is None:
        return None
    try:
        client = get_milvus_client()
        if not client.has_collection(settings.milvus_collection):
            return DocumentChunks(doc_id, row["doc_title"], 0, page, page_size, [])
        primary_source_id = _primary_source_id(doc_id)
        records = client.query(
            settings.milvus_collection,
            filter=f"doc_id == {doc_id}",
            output_fields=["id", "chunk_idx", "source", "chunk_text", "meta"],
            limit=16384,
            consistency_level="Strong",
        )
        if not isinstance(records, list):
            raise ValueError("invalid Milvus response")
        normalized: list[tuple[dict, dict, int | None]] = []
        for record in records:
            meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
            record_source_id = _optional_int(meta.get("source_id")) or primary_source_id
            if source_id is not None and record_source_id != source_id:
                continue
            normalized.append((record, meta, record_source_id))
        normalized.sort(key=lambda value: int(value[0].get("chunk_idx", 0)))
        total = len(normalized)
        offset = (page - 1) * page_size
        items: list[DocumentChunk] = []
        for record, meta, record_source_id in normalized[offset : offset + page_size]:
            text = str(record.get("chunk_text") or "")
            items.append(
                DocumentChunk(
                    chunk_id=str(record.get("id") or ""),
                    chunk_idx=int(record.get("chunk_idx") or 0),
                    text=text,
                    char_count=len(text),
                    source=_optional_str(record.get("source")),
                    article_no=_optional_str(meta.get("article_no")),
                    chapter=_optional_str(meta.get("chapter")),
                    content_type=_optional_str(meta.get("content_type")),
                    image_id=_optional_int(meta.get("image_id")),
                    page_no=_optional_int(meta.get("page_no")),
                    image_category=_optional_str(meta.get("image_category")),
                    source_id=record_source_id,
                    source_title=_optional_str(meta.get("source_title"))
                    or _source_title(record_source_id),
                    source_file_name=_optional_str(meta.get("source_file_name")),
                    source_chunk_idx=_optional_int(meta.get("source_chunk_idx"))
                    if meta.get("source_chunk_idx") is not None
                    else int(record.get("chunk_idx") or 0),
                )
            )
        return DocumentChunks(doc_id, row["doc_title"], total, page, page_size, items)
    except DocumentChunksUnavailableError:
        raise
    except Exception as exc:
        raise DocumentChunksUnavailableError("chunks unavailable") from exc


def promote_staging_document(staging_doc_id: int, target_doc_id: int) -> IngestResult:
    """Atomically promote a successfully ingested hidden staging document.

    Milvus has no cross-system transaction with PostgreSQL, so the target vectors are
    snapshotted and restored if the database promotion fails.
    """
    if staging_doc_id == target_doc_id:
        raise DocumentPromotionError("invalid staging target")
    staging = _load_document(staging_doc_id)
    target = _load_document(target_doc_id)
    if staging is None or target is None:
        raise DocumentNotFoundError("kb_document not found")
    if staging.get("status") != "staging" or staging.get("embedding_status") != EmbeddingStatus.SUCCESS:
        raise DocumentPromotionError("staging document is not ready")

    client = get_milvus_client()
    old_records = _query_full_chunk_records(target_doc_id, client)
    staging_records = _query_full_chunk_records(staging_doc_id, client)
    if not staging_records:
        raise DocumentPromotionError("staging document has no chunks")
    promoted = [_promoted_record(item, target_doc_id) for item in staging_records]
    promoted_ids = [item["id"] for item in promoted]
    old_objects: list[tuple[str | None, str | None]] = []
    try:
        client.upsert(settings.milvus_collection, data=promoted)
        ids_json = json.dumps(promoted_ids, ensure_ascii=False)
        client.delete(
            settings.milvus_collection,
            filter=f"doc_id == {target_doc_id} and id not in {ids_json}",
        )

        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            locked_target = db.execute(
                select(kb_document).where(kb_document.c.id == target_doc_id).with_for_update()
            ).mappings().first()
            locked_staging = db.execute(
                select(kb_document).where(kb_document.c.id == staging_doc_id).with_for_update()
            ).mappings().first()
            if (
                locked_target is None
                or locked_staging is None
                or locked_target["status"] != "active"
                or locked_staging["status"] != "staging"
            ):
                raise DocumentPromotionError("document state changed")

            old_attachment_id = locked_target["attachment_id"]
            new_attachment_id = locked_staging["attachment_id"]
            if old_attachment_id is None or new_attachment_id is None:
                raise DocumentPromotionError("attachment missing")
            old_attachment = db.execute(
                select(
                    sys_attachment.c.bucket,
                    sys_attachment.c.object_key,
                ).where(sys_attachment.c.id == old_attachment_id)
            ).mappings().first()
            if old_attachment:
                old_objects.append((old_attachment["bucket"], old_attachment["object_key"]))
            old_images = db.execute(
                select(kb_document_image.c.bucket_name, kb_document_image.c.object_key).where(
                    kb_document_image.c.document_id == target_doc_id
                )
            ).mappings().all()
            old_objects.extend((row["bucket_name"], row["object_key"]) for row in old_images)

            # Image rows are derived data and have a document/hash unique constraint;
            # remove the old rows before reassigning the staging rows.
            db.execute(delete(kb_document_image).where(kb_document_image.c.document_id == target_doc_id))
            db.execute(
                update(kb_document_image)
                .where(kb_document_image.c.document_id == staging_doc_id)
                .values(document_id=target_doc_id)
            )
            db.execute(
                update(sys_attachment)
                .where(sys_attachment.c.id == old_attachment_id)
                .values(status="inactive", deleted_at=now)
            )
            db.execute(
                update(sys_attachment)
                .where(sys_attachment.c.id == new_attachment_id)
                .values(biz_type="knowledge_base", status="active", deleted_at=None)
            )
            values = {
                "doc_title": locked_staging["doc_title"],
                "doc_type": locked_staging["doc_type"],
                "legal_category": locked_staging["legal_category"],
                "category_id": locked_staging["category_id"],
                "attachment_id": new_attachment_id,
                "content_text": locked_staging["content_text"],
                "description_summary": locked_staging["description_summary"],
                "body_markdown": locked_staging["body_markdown"],
                "embedding_status": locked_staging["embedding_status"],
                "extra_metadata": locked_staging["extra_metadata"],
                "vl_status": locked_staging["vl_status"],
                "image_total": locked_staging["image_total"],
                "image_kept": locked_staging["image_kept"],
                "image_filtered": locked_staging["image_filtered"],
                "vl_processed_at": locked_staging["vl_processed_at"],
                "upload_timings": locked_staging["upload_timings"],
                "ingest_timings": locked_staging["ingest_timings"],
                "remark": None,
                "updated_at": now,
            }
            db.execute(update(kb_document).where(kb_document.c.id == target_doc_id).values(**values))
            db.execute(
                update(kb_document)
                .where(kb_document.c.id == staging_doc_id)
                .values(status="replaced", deleted_at=now, updated_at=now)
            )
            db.commit()
    except Exception as exc:
        try:
            client.delete(settings.milvus_collection, filter=f"doc_id == {target_doc_id}")
            if old_records:
                client.upsert(settings.milvus_collection, data=old_records)
        except Exception:
            pass
        if isinstance(exc, (DocumentPromotionError, DocumentNotFoundError)):
            raise
        raise DocumentPromotionError("document promotion failed") from exc

    try:
        client.delete(settings.milvus_collection, filter=f"doc_id == {staging_doc_id}")
    except Exception:
        # Target promotion is already committed; a stale hidden staging chunk is
        # harmless because all search scopes are restricted to active documents.
        pass

    for bucket, object_key in old_objects:
        _remove_object_safely(bucket, object_key)
    counts = _image_counts_from_row(staging)
    return IngestResult(
        doc_id=target_doc_id,
        status=EmbeddingStatus.SUCCESS,
        chunk_count=len(promoted),
        vl_status=staging.get("vl_status") or "success",
        upload_timings=staging.get("upload_timings"),
        ingest_timings=staging.get("ingest_timings"),
        **counts,
    )


def cleanup_staging_document(staging_doc_id: int) -> None:
    """Best-effort cleanup for a failed staging replacement."""
    row = _load_document(staging_doc_id)
    if row is None or row.get("status") != "staging":
        return
    objects: list[tuple[str | None, str | None]] = []
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        attachment = db.execute(
            select(
                sys_attachment.c.bucket,
                sys_attachment.c.object_key,
                sys_attachment.c.biz_type,
            ).where(
                sys_attachment.c.id == row["attachment_id"]
            )
        ).mappings().first()
        if attachment:
            objects.append((attachment["bucket"], attachment["object_key"]))
        images = db.execute(
            select(kb_document_image.c.bucket_name, kb_document_image.c.object_key).where(
                kb_document_image.c.document_id == staging_doc_id
            )
        ).mappings().all()
        objects.extend((item["bucket_name"], item["object_key"]) for item in images)
        db.execute(delete(kb_document_image).where(kb_document_image.c.document_id == staging_doc_id))
        db.execute(
            update(kb_document)
            .where(kb_document.c.id == staging_doc_id)
            .values(status="cancelled", deleted_at=now, updated_at=now)
        )
        if (
            row["attachment_id"] is not None
            and attachment
            and attachment["biz_type"] == "knowledge_base_staging"
        ):
            db.execute(
                update(sys_attachment)
                .where(sys_attachment.c.id == row["attachment_id"])
                .values(status="inactive", deleted_at=now)
            )
        db.commit()
    try:
        get_milvus_client().delete(
            settings.milvus_collection, filter=f"doc_id == {staging_doc_id}"
        )
    except Exception:
        pass
    for bucket, object_key in objects:
        _remove_object_safely(bucket, object_key)


def purge_documents(doc_ids: list[int]) -> dict[str, int]:
    """Best-effort purge of derived artifacts for deleted documents.

    The caller (platform-api) is responsible for soft-deleting the
    kb_document / kb_document_source / sys_attachment rows. This function
    only cleans up Milvus chunks, kb_document_image rows and their MinIO
    objects. It is intentionally idempotent and swallow failures so that a
    failed purge can be retried without side effects.
    """
    if not doc_ids:
        return {"purged": 0, "images_removed": 0}

    objects: list[tuple[str | None, str | None]] = []
    with SessionLocal() as db:
        images = db.execute(
            select(
                kb_document_image.c.document_id,
                kb_document_image.c.bucket_name,
                kb_document_image.c.object_key,
            ).where(kb_document_image.c.document_id.in_(doc_ids))
        ).mappings().all()
        objects.extend(
            (item["bucket_name"], item["object_key"]) for item in images
        )
        db.execute(
            delete(kb_document_image).where(
                kb_document_image.c.document_id.in_(doc_ids)
            )
        )
        db.commit()

    client = get_milvus_client()
    for doc_id in doc_ids:
        try:
            client.delete(
                settings.milvus_collection,
                filter=f"doc_id == {doc_id}",
            )
        except Exception:
            pass

    for bucket, object_key in objects:
        _remove_object_safely(bucket, object_key)

    return {"purged": len(doc_ids), "images_removed": len(objects)}


def verify_restore_artifacts(doc_ids: list[int]) -> dict:
    """检查每个已软删文档恢复所需的 RAG 侧派生产物是否齐全。

    校验范围：
    - 成功文档（embedding_status='success'）的 Milvus chunks 必须仍存在；
    - 各文档的派生图片对象（kb_document_image 指向的 MinIO 对象）必须仍存在。

    原件（sys_attachment.object_key）由 platform-api 自行校验，本函数不负责。
    embedding_status != 'success' 的文档从未生成向量，跳过 chunk 校验。

    用 _count_chunks_strict（会抛错）而非 _count_chunks（会吞错）：恢复校验必须把
    Milvus 异常显式上报，避免把"服务故障"误判为"向量齐全"。
    """
    if not doc_ids:
        return {"items": []}

    with SessionLocal() as db:
        doc_rows = db.execute(
            select(
                kb_document.c.id,
                kb_document.c.embedding_status,
            ).where(kb_document.c.id.in_(doc_ids))
        ).mappings().all()
        embedding_by_doc = {
            int(r["id"]): r["embedding_status"] for r in doc_rows
        }

        image_rows = db.execute(
            select(
                kb_document_image.c.document_id,
                kb_document_image.c.bucket_name,
                kb_document_image.c.object_key,
            ).where(kb_document_image.c.document_id.in_(doc_ids))
        ).mappings().all()

    images_by_doc: dict[int, list[tuple[str | None, str | None]]] = {}
    for r in image_rows:
        images_by_doc.setdefault(int(r["document_id"]), []).append(
            (r["bucket_name"], r["object_key"])
        )

    items: list[dict] = []
    for doc_id in doc_ids:
        missing_chunks = 0
        missing_images: list[str] = []

        if embedding_by_doc.get(doc_id) == EmbeddingStatus.SUCCESS:
            try:
                if _count_chunks_strict(doc_id) == 0:
                    missing_chunks = 1
            except DocumentChunksUnavailableError:
                # Milvus 无法提供有效结果，按"向量不可用"处理，恢复前需排查。
                missing_chunks = 1

        for bucket, object_key in images_by_doc.get(doc_id, []):
            if not object_key:
                continue
            try:
                exists = minio_file_exists(object_key, bucket)
            except Exception:
                # 非 NoSuchKey 的异常（网络/权限等）也视为不可恢复，避免误判。
                exists = False
            if not exists:
                missing_images.append(object_key)

        items.append(
            {
                "doc_id": doc_id,
                "ok": missing_chunks == 0 and not missing_images,
                "missing_chunks": missing_chunks,
                "missing_images": missing_images,
            }
        )

    return {"items": items}


def build_document_markdown(
    doc_id: int, *, source_id: int | None = None
) -> DocumentMarkdown | None:
    """渲染一篇文档为 Markdown：标题 + 文档概述 + 轻量结构化正文 + 附图（预签名链接）。

    预签名 URL 现场生成（有过期时间），故整个 Markdown 请求时即时拼装。
    """
    row = _load_document(doc_id)
    if row is None:
        return None
    sources = _document_sources(doc_id)
    if source_id is not None:
        sources = [item for item in sources if int(item["id"]) == source_id]
        if not sources:
            return None
    images = _load_kept_images(doc_id)
    if sources:
        sections: list[str] = []
        for source in sources:
            body = (source["body_markdown"] or "").strip()
            if not body and bool(source["is_primary"]):
                body = (row.get("body_markdown") or "").strip()
            if not body:
                body = "_该来源尚无可预览的 Markdown；强制重建后生成。_"
            sections.append(f"# 来源：{source['source_title']}\n\n{body}")
        return DocumentMarkdown(
            doc_id=doc_id,
            doc_title=row["doc_title"],
            description_summary=(row.get("description_summary") or "").strip() or None,
            image_count=sum(int(item["image_total"] or 0) for item in sources),
            markdown=resolve_markdown_texts(sections and ["\n\n---\n\n".join(sections)] or [""])[0],
            source_count=len(sources),
            source_id=source_id,
        )
    description_summary = (row.get("description_summary") or "").strip() or None
    stored_markdown = (row.get("body_markdown") or "").strip()
    if stored_markdown:
        markdown = resolve_markdown_texts([stored_markdown])[0]
    else:
        body = _resolve_body_text(row)
        markdown = _render_document_markdown(
            title=row["doc_title"],
            body=body,
            description_summary=description_summary,
            images=images,
        )
    return DocumentMarkdown(
        doc_id=doc_id,
        doc_title=row["doc_title"],
        description_summary=description_summary,
        image_count=len(images),
        markdown=markdown,
        source_count=1,
        source_id=source_id,
    )


def _load_document(doc_id: int):
    with SessionLocal() as db:
        row = db.execute(
            select(
                kb_document.c.id,
                kb_document.c.doc_title,
                kb_document.c.doc_type,
                kb_document.c.legal_category,
                kb_document.c.category_id,
                kb_document.c.attachment_id,
                kb_document.c.content_text,
                kb_document.c.description_summary,
                kb_document.c.body_markdown,
                kb_document.c.embedding_status,
                kb_document.c.permission_level,
                kb_document.c.source_type,
                kb_document.c.biz_type,
                kb_document.c.biz_id,
                kb_document.c.case_id,
                kb_document.c.dossier_no,
                kb_document.c.extra_metadata,
                kb_document.c.upload_timings,
                kb_document.c.ingest_timings,
                kb_document.c.vl_status,
                kb_document.c.image_total,
                kb_document.c.image_kept,
                kb_document.c.image_filtered,
                kb_document.c.vl_processed_at,
                kb_document.c.remark,
                kb_document.c.updated_at,
                kb_document.c.deleted_at,
                kb_document.c.status,
            ).where(kb_document.c.id == doc_id)
        ).mappings().first()
    if row is None:
        return None
    document = dict(row)
    category = resolve_document_categories([doc_id]).get(doc_id)
    if category is not None:
        document["category_name"] = category.name
        document["category_path"] = category.path
        document["category_path_ids"] = category.path_ids
    return document


def _load_kept_images(doc_id: int) -> list:
    """取文档的保留图片（active + keep_for_rag），按出现顺序。"""
    with SessionLocal() as db:
        return db.execute(
            select(
                kb_document_image.c.id,
                kb_document_image.c.page_no,
                kb_document_image.c.image_index,
                kb_document_image.c.image_category,
                kb_document_image.c.description_text,
                kb_document_image.c.extracted_text,
                kb_document_image.c.bucket_name,
                kb_document_image.c.object_key,
            )
            .where(
                kb_document_image.c.document_id == doc_id,
                kb_document_image.c.status == "active",
                kb_document_image.c.keep_for_rag.is_(True),
            )
            .order_by(kb_document_image.c.image_index)
        ).mappings().all()


def _resolve_body_text(row) -> str:
    """渲染用正文：content_text 非空则用，否则从 MinIO 原件解析（复用入库解析逻辑）。"""
    content_text = (row["content_text"] or "").strip()
    if content_text:
        return content_text
    try:
        parsed, _ = _resolve_document(row, row.get("attachment_id"))
    except Exception:
        return ""
    return parsed.text or ""


def _render_document_markdown(
    *,
    title: str | None,
    body: str,
    description_summary: str | None,
    images: list,
) -> str:
    parts: list[str] = [f"# {title or '未命名文档'}"]
    if description_summary:
        parts.append(f"## 文档概述\n\n{description_summary}")
    body_md = chunker.to_markdown(body)
    if body_md:
        parts.append(f"## 正文\n\n{body_md}")
    if images:
        img_blocks = [_render_image_markdown(im) for im in images]
        parts.append("## 附图\n\n" + "\n\n".join(img_blocks))
    return "\n\n".join(parts)


def _render_image_markdown(image) -> str:
    category = image["image_category"] or "other"
    page = image["page_no"]
    page_label = f"第{page}页" if page else "页码未知"
    desc = (image["description_text"] or "").strip()
    alt = (desc[:40] + "…") if len(desc) > 40 else (desc or category)
    lines = [f"### {category} · {page_label}"]
    object_key = image["object_key"]
    if object_key:
        try:
            url = minio_presigned_url(object_key, bucket=image["bucket_name"])
            lines.append(f"![{alt}]({url})")
        except Exception:
            # 预签名失败不阻断整篇渲染；附图区标注不可访问。
            lines.append(f"![{alt}](图片链接生成失败)")
    if desc:
        lines.append(desc)
    extracted = (image.get("extracted_text") or "").strip()
    if extracted:
        lines.append(f"**图片识别文字：** {extracted}")
    return "\n\n".join(lines)


def image_presigned_map(image_ids: list[int]) -> dict[int, str]:
    """批量读取图片对象并生成预签名 URL；失败图片不进入结果。"""
    ids = list(dict.fromkeys(int(value) for value in image_ids if value is not None))
    if not ids:
        return {}
    with SessionLocal() as db:
        rows = db.execute(
            select(
                kb_document_image.c.id,
                kb_document_image.c.bucket_name,
                kb_document_image.c.object_key,
            ).where(
                kb_document_image.c.id.in_(ids),
                kb_document_image.c.status == "active",
                kb_document_image.c.keep_for_rag.is_(True),
            )
        ).mappings().all()
    result: dict[int, str] = {}
    for row in rows:
        if not row["object_key"]:
            continue
        try:
            result[int(row["id"])] = minio_presigned_url(
                row["object_key"], bucket=row["bucket_name"]
            )
        except Exception:
            continue
    return result


def resolve_markdown_texts(texts: list[str]) -> list[str]:
    """一次 DB 批查解析一组 Markdown 中的图片占位符。"""
    ids: list[int] = []
    for value in texts:
        ids.extend(markdown_utils.extract_image_ids(value))
    urls = image_presigned_map(ids)
    return [markdown_utils.resolve_image_refs(value, urls) for value in texts]


def _resolve_document(row, attachment_id: int | None) -> tuple[ParsedDocument, str]:
    """解析原件获取图片；content_text 非空时只覆盖解析出来的正文。"""
    content_text = (row["content_text"] or "").strip()
    if attachment_id is None:
        if not content_text:
            raise RuntimeError("no content_text and no attachment_id")
        return parser.from_text(content_text), _sha256(content_text.encode("utf-8"))

    with SessionLocal() as db:
        attachment = db.execute(
            select(
                sys_attachment.c.file_name,
                sys_attachment.c.file_ext,
                sys_attachment.c.bucket,
                sys_attachment.c.object_key,
            ).where(sys_attachment.c.id == attachment_id)
        ).mappings().first()
    if attachment is None:
        if content_text:
            return parser.from_text(content_text), _sha256(content_text.encode("utf-8"))
        raise RuntimeError(f"sys_attachment {attachment_id} not found")
    if not attachment["object_key"] or not attachment["bucket"]:
        if content_text:
            return parser.from_text(content_text), _sha256(content_text.encode("utf-8"))
        raise RuntimeError("attachment has no object_key/bucket (NAS file?)")

    content = minio_download(attachment["object_key"], attachment["bucket"])
    file_ext = attachment["file_ext"] or _ext_from_filename(attachment["file_name"])
    try:
        parsed = parser.parse(
            content,
            file_ext,
            scan_page_min_text_chars=settings.scan_page_min_text_chars,
            pdf_render_scale=settings.pdf_render_scale,
        )
    except UnsupportedFileTypeError:
        if not content_text:
            raise
        parsed = parser.from_text(content_text)
    if content_text:
        override = parser.from_text(content_text)
        order = len(override.nodes)
        image_nodes = [
            ContentNode(
                kind="image",
                order=order + index,
                page_no=image.page_no,
                image_sha256=image.sha256,
            )
            for index, image in enumerate(parsed.images)
        ]
        parsed = ParsedDocument(
            text_blocks=override.text_blocks,
            images=parsed.images,
            nodes=override.nodes + image_nodes,
            metadata=parsed.metadata,
        )
    return parsed, _sha256(content)


def _analyze_images(images, *, doc_title: str) -> list[ImageAnalysis]:
    analyses: list[ImageAnalysis] = []
    candidates = []
    for image in images:
        decision = image_filter.prefilter(image)
        if decision is not None:
            analyses.append(decision)
        else:
            candidates.append(image)
    if not candidates:
        return sorted(analyses, key=lambda item: item.asset.image_index)

    workers = max(1, min(settings.vl_concurrency, len(candidates), 100))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="qwen-vl") as executor:
        futures = {
            executor.submit(vl.analyze, image, doc_title=doc_title): image
            for image in candidates
        }
        for future in as_completed(futures):
            image = futures[future]
            try:
                analyses.append(future.result())
            except Exception as exc:
                analyses.append(vl.failed_analysis(image, exc))
    return sorted(analyses, key=lambda item: item.asset.image_index)


def _analyze_images_after_draft(
    images,
    *,
    doc_title: str,
    image_ids: dict[str, int],
    contexts: dict[int, str],
    stored_hashes: set[str],
) -> list[ImageAnalysis]:
    """在 Markdown draft 已形成后分析图片，并把所属 chunk 作为 VL 上下文。"""
    analyses: list[ImageAnalysis] = []
    candidates: list = []
    for image in images:
        if image.sha256 not in stored_hashes:
            analyses.append(vl.failed_analysis(image, RuntimeError("derived image upload failed")))
            continue
        decision = image_filter.prefilter(image)
        if decision is not None:
            analyses.append(decision)
        else:
            candidates.append(image)
    if not candidates:
        return sorted(analyses, key=lambda item: item.asset.image_index)

    workers = max(1, min(settings.vl_concurrency, len(candidates), 100))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="qwen-vl") as executor:
        futures = {}
        for image in candidates:
            image_id = image_ids.get(image.sha256)
            context = markdown_utils.strip_for_llm(contexts.get(image_id, ""))
            future = executor.submit(
                vl.analyze,
                image,
                doc_title=doc_title,
                context_text=context,
            )
            futures[future] = image
        for future in as_completed(futures):
            image = futures[future]
            try:
                analyses.append(future.result())
            except Exception as exc:
                analyses.append(vl.failed_analysis(image, exc))
    return sorted(analyses, key=lambda item: item.asset.image_index)


def _store_pending_images(
    doc_id: int,
    *,
    attachment_id: int | None,
    source_hash: str,
    images: list,
) -> tuple[dict[str, int], set[str]]:
    """先保存原图并建立 pending 记录；此函数不执行 VL。"""
    now = datetime.now(timezone.utc)
    ids: dict[str, int] = {}
    stored_hashes: set[str] = set()
    with SessionLocal() as db:
        db.execute(
            update(kb_document_image)
            .where(kb_document_image.c.document_id == doc_id)
            .values(status="inactive", deleted_at=now, updated_at=now)
        )
        for asset in images:
            bucket_name: str | None = None
            object_key: str | None = None
            upload_error: str | None = None
            try:
                object_key = f"rag-derived/{doc_id}/{source_hash}/{asset.sha256}.{asset.extension}"
                bucket_name, object_key = upload_derived(
                    object_key, asset.content, content_type=asset.mime_type
                )
                stored_hashes.add(asset.sha256)
            except Exception as exc:
                upload_error = f"derived image upload failed ({type(exc).__name__})"

            values = {
                "document_id": doc_id,
                "attachment_id": attachment_id,
                "page_no": asset.page_no,
                "page_numbers": asset.page_numbers,
                "image_index": asset.image_index,
                "image_sha256": asset.sha256,
                "width": asset.width,
                "height": asset.height,
                "mime_type": asset.mime_type,
                "bucket_name": bucket_name,
                "object_key": object_key,
                "image_category": None,
                "keep_for_rag": upload_error is None,
                "filter_reason": None,
                "confidence": None,
                "description_text": None,
                "extracted_text": None,
                "vl_status": "pending" if upload_error is None else "failed",
                "vl_model": None,
                "prompt_version": settings.vl_prompt_version,
                "prompt_tokens": None,
                "completion_tokens": None,
                "error_message": upload_error,
                "updated_at": now,
                "deleted_at": None,
                "status": "active",
            }
            statement = (
                pg_insert(kb_document_image)
                .values(created_at=now, **values)
                .on_conflict_do_update(
                    constraint="uk_kb_document_image_doc_hash", set_=values
                )
                .returning(kb_document_image.c.id)
            )
            image_id = db.execute(statement).scalar_one()
            ids[asset.sha256] = int(image_id)
        db.commit()
    return ids, stored_hashes


def _update_image_analyses(doc_id: int, analyses: list[ImageAnalysis]) -> None:
    """把 draft 切片后产生的 VL/预筛结果写回 pending 图片记录。"""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        for analysis in analyses:
            db.execute(
                update(kb_document_image)
                .where(
                    kb_document_image.c.document_id == doc_id,
                    kb_document_image.c.image_sha256 == analysis.asset.sha256,
                    kb_document_image.c.status == "active",
                )
                .values(
                    image_category=analysis.category,
                    keep_for_rag=(
                        analysis.status == "success" and analysis.keep_for_rag
                    ),
                    filter_reason=analysis.filter_reason,
                    confidence=analysis.confidence,
                    description_text=analysis.description or None,
                    extracted_text=analysis.extracted_text or None,
                    vl_status=analysis.status,
                    vl_model=(
                        settings.vl_model if analysis.status == "success" else None
                    ),
                    prompt_version=settings.vl_prompt_version,
                    prompt_tokens=analysis.prompt_tokens,
                    completion_tokens=analysis.completion_tokens,
                    error_message=analysis.error_message,
                    updated_at=now,
                )
            )
        db.commit()


def _store_image_analyses(
    doc_id: int,
    *,
    attachment_id: int | None,
    source_hash: str,
    analyses: list[ImageAnalysis],
) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    ids: dict[str, int] = {}
    with SessionLocal() as db:
        db.execute(
            update(kb_document_image)
            .where(kb_document_image.c.document_id == doc_id)
            .values(status="inactive", deleted_at=now, updated_at=now)
        )
        for analysis in analyses:
            asset = analysis.asset
            bucket_name: str | None = None
            object_key: str | None = None
            try:
                object_key = (
                    f"rag-derived/{doc_id}/{source_hash}/{asset.sha256}.{asset.extension}"
                )
                bucket_name, object_key = upload_derived(
                    object_key, asset.content, content_type=asset.mime_type
                )
            except Exception:
                # 派生图仅用于审计，存储失败不阻断 VL 描述和文本入库。
                bucket_name = None
                object_key = None
            values = {
                "document_id": doc_id,
                "attachment_id": attachment_id,
                "page_no": asset.page_no,
                "page_numbers": asset.page_numbers,
                "image_index": asset.image_index,
                "image_sha256": asset.sha256,
                "width": asset.width,
                "height": asset.height,
                "mime_type": asset.mime_type,
                "bucket_name": bucket_name,
                "object_key": object_key,
                "image_category": analysis.category,
                "keep_for_rag": analysis.keep_for_rag,
                "filter_reason": analysis.filter_reason,
                "confidence": analysis.confidence,
                "description_text": analysis.description or None,
                "extracted_text": analysis.extracted_text or None,
                "vl_status": analysis.status,
                "vl_model": settings.vl_model if analysis.status != "filtered" else None,
                "prompt_version": settings.vl_prompt_version,
                "prompt_tokens": analysis.prompt_tokens,
                "completion_tokens": analysis.completion_tokens,
                "error_message": analysis.error_message,
                "updated_at": now,
                "deleted_at": None,
                "status": "active",
            }
            statement = (
                pg_insert(kb_document_image)
                .values(created_at=now, **values)
                .on_conflict_do_update(
                    constraint="uk_kb_document_image_doc_hash", set_=values
                )
                .returning(kb_document_image.c.id)
            )
            image_id = db.execute(statement).scalar_one()
            ids[asset.sha256] = image_id
        db.commit()
    return ids


def _build_vector_chunks(
    doc_id: int,
    document: ParsedDocument,
    analyses: list[ImageAnalysis],
    image_ids: dict[str, int],
) -> list[_VectorChunk]:
    text_chunks = chunker.split(
        document.text,
        settings.chunk_size,
        settings.chunk_overlap,
        by_article=settings.chunk_by_article,
    )
    result = [
        _VectorChunk(
            stable_id=f"{doc_id}:t:{item.idx:04d}",
            idx=item.idx,
            text=item.text,
            content_type="text",
            article_no=item.article_no,
            chapter=item.chapter,
        )
        for item in text_chunks
    ]
    next_idx = len(result)
    for analysis in analyses:
        if not (
            analysis.status == "success"
            and analysis.keep_for_rag
            and analysis.searchable_text
        ):
            continue
        image_id = image_ids[analysis.asset.sha256]
        page_label = f"第{analysis.asset.page_no}页" if analysis.asset.page_no else "页码未知"
        text = f"[图片说明][{page_label}][{analysis.category or 'other'}]\n{analysis.searchable_text}"
        result.append(
            _VectorChunk(
                stable_id=f"{doc_id}:i:{image_id}",
                idx=next_idx,
                text=text,
                content_type="image_description",
                image_id=image_id,
                page_no=analysis.asset.page_no,
                image_category=analysis.category,
            )
        )
        next_idx += 1
    return result


def _build_markdown_vector_chunks(
    doc_id: int,
    chunks: list[markdown_builder.MarkdownChunk],
    analyses_by_id: dict[int, ImageAnalysis],
) -> list[_VectorChunk]:
    """把最终 Markdown chunk 转为 Milvus 写入对象。"""
    result: list[_VectorChunk] = []
    for item in chunks:
        image_id = item.image_ids[0] if len(item.image_ids) == 1 else None
        analysis = analyses_by_id.get(image_id) if image_id is not None else None
        result.append(
            _VectorChunk(
                stable_id=f"{doc_id}:m:{item.idx:04d}",
                idx=item.idx,
                text=item.text,
                content_type="markdown",
                article_no=item.article_no,
                chapter=item.chapter,
                image_id=image_id,
                page_no=analysis.asset.page_no if analysis else None,
                image_category=analysis.category if analysis else None,
            )
        )
    return result


def _build_records(doc_id, row, chunks, dense, sparse) -> list[dict]:
    source = (
        row.get("category_name") or row["legal_category"] or row["doc_type"] or ""
    )[:100]
    records = []
    for item, dense_vector, sparse_vector in zip(chunks, dense, sparse):
        records.append(
            {
                "id": item.stable_id,
                "doc_id": doc_id,
                "chunk_idx": item.idx,
                "source": source,
                "chunk_text": item.text[:_CHUNK_TEXT_MAX],
                "dense": dense_vector,
                "sparse": sparse_vector,
                "meta": {
                    "doc_title": row["doc_title"],
                    "article_no": item.article_no,
                    "chapter": item.chapter,
                    "content_type": item.content_type,
                    "image_id": item.image_id,
                    "page_no": item.page_no,
                    "image_category": item.image_category,
                    "source_type": row["source_type"],
                    "biz_type": row["biz_type"],
                    "biz_id": row["biz_id"],
                    "case_id": row["case_id"],
                    "dossier_no": row["dossier_no"],
                    "permission_level": row["permission_level"],
                    "category_id": row.get("category_id"),
                    "category_path": row.get("category_path") or [source],
                },
            }
        )
    return records


def _derive_vl_status(analyses: list[ImageAnalysis]) -> str:
    if not analyses:
        return "success"
    failed = sum(item.status == "failed" for item in analyses)
    successful = sum(item.status in {"success", "filtered"} for item in analyses)
    if failed and successful:
        return "partial"
    if failed:
        return "failed"
    return "success"


def _cloud_disabled_image_analyses(images: list) -> list[ImageAnalysis]:
    """保留本地提取图片，但明确标记本次任务未调用云端 VL。"""
    return [
        ImageAnalysis(
            asset=image,
            status="filtered",
            category="page_scan" if image.is_page_scan else None,
            keep_for_rag=False,
            filter_reason="cloud_analysis_disabled",
        )
        for image in images
    ]


def _image_counts(analyses: list[ImageAnalysis]) -> dict[str, int]:
    return {
        "image_total": len(analyses),
        "image_kept": sum(
            item.status == "success" and item.keep_for_rag for item in analyses
        ),
        "image_filtered": sum(not item.keep_for_rag and item.status != "failed" for item in analyses),
    }


def _generate_doc_description(
    doc_title: str, document: ParsedDocument, analyses: list[ImageAnalysis]
) -> str | None:
    """入库成功后生成文档级中文摘要；开关关闭或失败返回 None，不阻断入库。"""
    if not settings.kb_generate_description:
        return None
    image_summaries = [
        a.searchable_text
        for a in analyses
        if a.status == "success" and a.keep_for_rag and a.searchable_text
    ]
    return describe.generate_description(
        doc_title=doc_title,
        body_text=document.text,
        image_summaries=image_summaries,
    )


def _set_vl_summary(
    doc_id: int,
    *,
    vl_status: str,
    image_total: int,
    image_kept: int,
    image_filtered: int,
) -> None:
    with SessionLocal() as db:
        db.execute(
            update(kb_document)
            .where(kb_document.c.id == doc_id)
            .values(
                vl_status=vl_status,
                image_total=image_total,
                image_kept=image_kept,
                image_filtered=image_filtered,
                vl_processed_at=datetime.now(timezone.utc),
            )
        )
        db.commit()


_SET_UNSET = object()  # 哨兵：区分“未传 description_summary”与“显式传 None”


def _set_status(
    doc_id: int,
    status: str,
    *,
    attachment_id: int | None,
    error_code: str | None = None,
    vl_status: str | None = None,
    image_total: int | None = None,
    image_kept: int | None = None,
    image_filtered: int | None = None,
    description_summary: object = _SET_UNSET,
    body_markdown: object = _SET_UNSET,
) -> None:
    with SessionLocal() as db:
        values: dict = {"embedding_status": status}
        if error_code is not None:
            values["remark"] = error_code[:500]
        elif status in {EmbeddingStatus.PROCESSING, EmbeddingStatus.SUCCESS}:
            values["remark"] = None
        if vl_status is not None:
            values["vl_status"] = vl_status
            if vl_status in {"success", "partial", "failed"}:
                values["vl_processed_at"] = datetime.now(timezone.utc)
        for name, value in (
            ("image_total", image_total),
            ("image_kept", image_kept),
            ("image_filtered", image_filtered),
        ):
            if value is not None:
                values[name] = value
        if description_summary is not _SET_UNSET:
            values["description_summary"] = description_summary
        if body_markdown is not _SET_UNSET:
            values["body_markdown"] = body_markdown
        db.execute(update(kb_document).where(kb_document.c.id == doc_id).values(**values))
        if attachment_id is not None:
            db.execute(
                update(sys_attachment)
                .where(sys_attachment.c.id == attachment_id)
                .values(ai_index_status=status)
            )
        db.commit()


def _set_ingest_timings(doc_id: int, report: dict) -> None:
    with SessionLocal() as db:
        db.execute(
            update(kb_document)
            .where(kb_document.c.id == doc_id)
            .values(ingest_timings=report)
        )
        db.commit()


def _sync_primary_source(doc_id: int, chunk_count: int, report: dict) -> None:
    """Keep the backfilled/new primary source in sync with legacy single-file ingest."""
    row = _load_document(doc_id)
    if row is None:
        return
    with SessionLocal() as db:
        db.execute(
            update(kb_document_source)
            .where(
                kb_document_source.c.document_id == doc_id,
                kb_document_source.c.is_primary.is_(True),
                kb_document_source.c.deleted_at.is_(None),
                kb_document_source.c.status == "active",
            )
            .values(
                ingest_status="success",
                chunk_count=chunk_count,
                image_total=int(row.get("image_total") or 0),
                image_kept=int(row.get("image_kept") or 0),
                image_filtered=int(row.get("image_filtered") or 0),
                body_markdown=row.get("body_markdown"),
                description_summary=row.get("description_summary"),
                ingest_timings=report,
                updated_at=datetime.now(timezone.utc),
            )
        )
        db.commit()


def _count_chunks(doc_id: int) -> int:
    try:
        client = get_milvus_client()
        if not client.has_collection(settings.milvus_collection):
            return 0
        result = client.query(
            settings.milvus_collection,
            filter=f"doc_id == {doc_id}",
            output_fields=["id"],
            limit=16384,
            consistency_level="Strong",
        )
        return len(result)
    except Exception:
        return 0


def _count_chunks_strict(doc_id: int, *, client=None) -> int:
    milvus = client or get_milvus_client()
    result = milvus.query(
        settings.milvus_collection,
        filter=f"doc_id == {doc_id}",
        output_fields=["id"],
        limit=16384,
        consistency_level="Strong",
    )
    if not isinstance(result, list):
        raise DocumentChunksUnavailableError("chunks unavailable")
    return len(result)


def _optional_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _document_sources(doc_id: int) -> list:
    with SessionLocal() as db:
        return list(
            db.execute(
                select(kb_document_source)
                .where(
                    kb_document_source.c.document_id == doc_id,
                    kb_document_source.c.deleted_at.is_(None),
                    kb_document_source.c.status == "active",
                )
                .order_by(kb_document_source.c.sort_order, kb_document_source.c.id)
            ).mappings().all()
        )


def _primary_source_id(doc_id: int) -> int | None:
    sources = _document_sources(doc_id)
    primary = next((item for item in sources if item["is_primary"]), None)
    return int(primary["id"]) if primary else None


def _source_title(source_id: int | None) -> str | None:
    if source_id is None:
        return None
    with SessionLocal() as db:
        value = db.execute(
            select(kb_document_source.c.source_title).where(
                kb_document_source.c.id == source_id,
                kb_document_source.c.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
    return str(value) if value else None


def _query_full_chunk_records(doc_id: int, client) -> list[dict]:
    result = client.query(
        settings.milvus_collection,
        filter=f"doc_id == {doc_id}",
        output_fields=[
            "id",
            "doc_id",
            "chunk_idx",
            "source",
            "chunk_text",
            "dense",
            "sparse",
            "meta",
        ],
        limit=16384,
        consistency_level="Strong",
    )
    if not isinstance(result, list):
        raise DocumentPromotionError("invalid Milvus response")
    return result


def _promoted_record(record: dict, target_doc_id: int) -> dict:
    chunk_idx = int(record.get("chunk_idx") or 0)
    old_id = str(record.get("id") or "")
    marker = ":i:" if ":i:" in old_id else ":m:"
    suffix = old_id.split(marker, 1)[1] if marker in old_id else f"{chunk_idx:04d}"
    return {
        "id": f"{target_doc_id}{marker}{suffix}",
        "doc_id": target_doc_id,
        "chunk_idx": chunk_idx,
        "source": record.get("source") or "",
        "chunk_text": record.get("chunk_text") or "",
        "dense": record.get("dense"),
        "sparse": record.get("sparse"),
        "meta": record.get("meta") or {},
    }


def _image_counts_from_row(row) -> dict[str, int]:
    return {
        "image_total": int(row.get("image_total") or 0),
        "image_kept": int(row.get("image_kept") or 0),
        "image_filtered": int(row.get("image_filtered") or 0),
    }


def _remove_object_safely(bucket: str | None, object_key: str | None) -> None:
    if not bucket or not object_key:
        return
    try:
        get_minio_client().remove_object(bucket, object_key)
    except Exception:
        pass


def _ext_from_filename(filename: str | None) -> str:
    if not filename:
        return ""
    return filename.rsplit(".", 1)[-1] if "." in filename else ""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
