"""造测试数据：上传本地文件到 MinIO + 插 sys_attachment + kb_document。

content_text 故意留 NULL，强制入库链走 MinIO 原件解析路径。

用法（在 law-rag-kb 目录）：
    python scripts/seed_test_doc.py [本地文件路径]

打印新建的 doc_id，供  curl -X POST http://localhost:8000/documents/{doc_id}/ingest  使用。
"""
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

# 让脚本能 import app 包（脚本在 law-rag-kb/scripts/，app 在 law-rag-kb/app/）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.minio_client import get_minio_client  # noqa: E402

DEFAULT_FILE = (
    Path(__file__).resolve().parent.parent.parent / "test_files" / "sample_test_upload.pdf"
)

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
    local_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FILE
    if not local_path.exists():
        print(f"file not found: {local_path}", file=sys.stderr)
        sys.exit(1)

    data = local_path.read_bytes()
    ext = local_path.suffix.lower()  # .pdf
    mime = _MIME.get(ext, "application/octet-stream")
    object_key = f"kb-test/{local_path.name}"

    # 1. 上传 MinIO（覆盖同名，便于重复验证）
    client = get_minio_client()
    client.put_object(
        settings.minio_bucket, object_key, BytesIO(data), len(data), content_type=mime
    )
    print(f"uploaded: {settings.minio_bucket}/{object_key} ({len(data)} bytes)")

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        # 拿一个 employee id 作为上传人/审计人
        emp = db.execute(
            text("SELECT id FROM oa.sys_employee ORDER BY id LIMIT 1")
        ).scalar()
        if emp is None:
            print(
                "sys_employee 为空——请先在 law-rag-service 跑 seed_test_data.py 造基础数据",
                file=sys.stderr,
            )
            sys.exit(1)

        # 2. 插 sys_attachment（填齐 NOT NULL 列；bucket/object_key/etag 来自 MinIO 上传）
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
                "fname": local_path.name,
                "ext": ext.lstrip("."),
                "mime": mime,
                "size": len(data),
                "obj": object_key,
                "emp": emp,
                "now": now,
                "bucket": settings.minio_bucket,
            },
        ).scalar()
        db.commit()
        print(f"sys_attachment id={att_id}")

        # 3. 插 kb_document（content_text=NULL 强制走 MinIO 解析）
        doc_id = db.execute(
            text(
                """
                INSERT INTO oa.kb_document
                  (doc_title, doc_type, legal_category, category_id,
                   attachment_id, content_text,
                   embedding_status, version_no, permission_level,
                   created_at, created_by, updated_at, updated_by, status)
                VALUES
                  (:title, '法律', '法律',
                   (SELECT id FROM oa.kb_category WHERE category_code = 'legal_law'),
                   :att, NULL,
                   'pending', 'v1', 'public',
                   :now, :emp, :now, :emp, 'active')
                RETURNING id
                """
            ),
            {"title": local_path.stem, "att": att_id, "now": now, "emp": emp},
        ).scalar()
        db.commit()
        print(f"kb_document id={doc_id}")

    print(f"\n下一步：curl -X POST http://localhost:8000/documents/{doc_id}/ingest")


if __name__ == "__main__":
    main()
