"""批量入库脚本：遍历 test_files/ 子目录 → MinIO + sys_attachment + kb_document → 调 ingest 入库。

子目录名映射 legal_category / doc_type：法律法规→法规、判决案例→案例、案件材料→案件材料、工作资料→工作资料。
幂等：按 object_key 查已有 sys_attachment / kb_document，已存在则复用 doc_id（不重复建表）；
入库状态按 ingest_document 自身状态机（已 success 默认 SKIPPED，--force 强制重跑）。

用法（在 law-rag-kb 目录）：
    python scripts/batch_ingest.py            # 新文件入库，已 success 的跳过
    python scripts/batch_ingest.py --force    # 已入库的也强制重跑
"""
import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

# 让脚本能 import app 包，并把 cwd 固定到 law-rag-kb（config 的 .env 依赖 cwd）
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

from sqlalchemy import select, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.minio_client import get_minio_client  # noqa: E402
from app.ingest import service as ingest_service  # noqa: E402
from app.models.tables import kb_document, sys_attachment  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent / "test_files"

# 子目录 → legal_category / doc_type
CATEGORY_MAP = {
    "法律法规": "法规",
    "判决案例": "案例",
    "案件材料": "案件材料",
    "工作资料": "工作资料",
}
SUPPORTED_EXT = {
    ".pdf", ".docx", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff",
}
_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="批量入库 test_files/ 法律文档")
    parser.add_argument("--force", action="store_true", help="已入库的也强制重跑")
    args = parser.parse_args()

    if not ROOT.exists():
        print(f"test_files not found: {ROOT}", file=sys.stderr)
        sys.exit(1)

    files = []
    for sub in sorted(ROOT.iterdir()):
        if sub.is_dir() and sub.name in CATEGORY_MAP:
            for f in sorted(sub.iterdir()):
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXT:
                    files.append((sub, f))
    print(f"found {len(files)} supported files under {ROOT}")

    emp = _get_emp()
    results = [_ingest_one(sub, f, emp, force=args.force) for sub, f in files]

    print("\n===== 批量入库汇总 =====")
    c = Counter(r["status"] for r in results)
    print(
        f"total={len(results)} | success={c.get('success', 0)} "
        f"skipped={c.get('skipped', 0)} failed={c.get('failed', 0)}"
    )
    for r in results:
        print(
            f"  [{r['status']:8s}] {r['category']}/{r['name']} "
            f"doc_id={r['doc_id']} chunks={r['chunks']} {r['msg']}"
        )


def _ingest_one(sub: Path, f: Path, emp: int, *, force: bool) -> dict:
    category = CATEGORY_MAP[sub.name]
    ext = f.suffix.lower()
    object_key = f"kb-batch/{sub.name}/{f.name}"
    rec: dict = {
        "category": sub.name,
        "name": f.name,
        "doc_id": None,
        "status": "failed",
        "chunks": 0,
        "msg": "",
    }
    data = f.read_bytes()
    mime = _MIME.get(ext, "application/octet-stream")

    # 1. 上传 MinIO（覆盖同名，便于重复验证）
    try:
        client = get_minio_client()
        client.put_object(
            settings.minio_bucket, object_key, BytesIO(data), len(data), content_type=mime
        )
    except Exception as e:
        rec["msg"] = f"minio upload: {e}"[:120]
        return rec

    # 2. 幂等建/查 sys_attachment + kb_document
    now = datetime.now(timezone.utc)
    try:
        doc_id = _ensure_records(object_key, f, ext, mime, len(data), category, emp, now)
    except Exception as e:
        rec["msg"] = f"ensure records: {e}"[:120]
        return rec
    rec["doc_id"] = doc_id

    # 3. 入库（状态机自带幂等：已 success 默认 SKIPPED，force 强制重跑）
    try:
        res = ingest_service.ingest_document(doc_id, force=force)
        rec["status"] = res.status
        rec["chunks"] = res.chunk_count
        rec["msg"] = (res.message or "")[:120]
    except Exception as e:
        rec["msg"] = f"ingest: {e}"[:120]
    return rec


def _ensure_records(
    object_key: str, f: Path, ext: str, mime: str, size: int, category: str, emp: int, now
) -> int:
    """幂等：按 object_key 查 attachment / kb_document，缺则补建，返回 doc_id。"""
    with SessionLocal() as db:
        att_id = db.execute(
            select(sys_attachment.c.id).where(sys_attachment.c.object_key == object_key)
        ).scalar()
        created = False

        if att_id is None:
            att_id = db.execute(
                text(
                    """
                    INSERT INTO oa.sys_attachment
                      (biz_type, biz_id, file_name, file_ext, mime_type, file_size,
                       storage_type, storage_path, file_hash, ocr_text,
                       uploaded_by, uploaded_at, ai_index_status,
                       original_file_name, current_file_name, file_exists_flag,
                       bucket, object_key,
                       created_at, created_by, updated_at, updated_by, status)
                    VALUES
                      ('document', 0, :fname, :ext, :mime, :size,
                       'minio', :obj, '', '',
                       :emp, :now, 'pending',
                       :fname, :fname, 'Y',
                       :bucket, :obj,
                       :now, :emp, :now, :emp, 'active')
                    RETURNING id
                    """
                ),
                {
                    "fname": f.name,
                    "ext": ext.lstrip("."),
                    "mime": mime,
                    "size": size,
                    "obj": object_key,
                    "emp": emp,
                    "now": now,
                    "bucket": settings.minio_bucket,
                },
            ).scalar()
            created = True

        doc_id = db.execute(
            select(kb_document.c.id).where(kb_document.c.attachment_id == att_id)
        ).scalar()
        if doc_id is None:
            doc_id = db.execute(
                text(
                    """
                    INSERT INTO oa.kb_document
                      (doc_title, doc_type, legal_category, attachment_id, content_text,
                       embedding_status, version_no, permission_level,
                       created_at, created_by, updated_at, updated_by, status)
                    VALUES
                      (:title, :cat, :cat, :att, NULL,
                       'pending', 'v1', 'public',
                       :now, :emp, :now, :emp, 'active')
                    RETURNING id
                    """
                ),
                {"title": f.stem, "cat": category, "att": att_id, "now": now, "emp": emp},
            ).scalar()
            created = True

        if created:
            db.commit()
    return doc_id


def _get_emp() -> int:
    with SessionLocal() as db:
        emp = db.execute(text("SELECT id FROM oa.sys_employee ORDER BY id LIMIT 1")).scalar()
    if emp is None:
        print(
            "sys_employee 为空——请先在 law-rag-service 跑 seed_test_data.py 造基础数据",
            file=sys.stderr,
        )
        sys.exit(1)
    return emp


if __name__ == "__main__":
    main()
