# -*- coding: utf-8 -*-
"""attachment_service 端到端验证（幂等，可重跑）。

流程：清理上轮 → 上传 → 校验 sys_attachment 字段 → MinIO 对象存在 → 下载一致
     → 预签名 URL → relation 关联 → 软删 + MinIO 删除。
"""
import sys
from datetime import timezone, datetime
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.services.attachment_service import attachment_service
from app.services.minio_service import minio_service
from app.models.oa_system import SysAttachment

CONTENT = "minio 附件业务绑定端到端验证 测试证据清单".encode("utf-8")
FILENAME = "_attachment_service_probe.pdf"
CATEGORY = "evidence"
BIZ_TYPE = "case"
ENTITY_TYPE = "case"
FILE_USAGE = 2  # attachment_usage: 2=证据材料


def cleanup(session):
    rows = session.execute(
        text("SELECT id, object_key FROM oa.sys_attachment WHERE file_name=:fn"),
        {"fn": FILENAME},
    ).fetchall()
    for aid, ok in rows:
        session.execute(
            text("DELETE FROM oa.sys_attachment_relation WHERE attachment_id=:a"),
            {"a": aid},
        )
        if ok:
            try:
                minio_service.delete_file(ok)
            except Exception:
                pass
        session.execute(text("DELETE FROM oa.sys_attachment WHERE id=:a"), {"a": aid})
    session.commit()
    return len(rows)


def main():
    with SessionLocal() as session:
        # 0. ensure bucket + 清理上轮
        minio_service.ensure_bucket()
        n = cleanup(session)
        print(f"[0] 清理上轮测试附件 {n} 条")

        # 1. 取一个 case 与一个员工
        case = session.execute(
            text("SELECT id, case_no FROM oa.case_main ORDER BY id DESC LIMIT 1")
        ).first()
        assert case, "数据库无 case_main 数据，请先跑 tmp_case_management_flow_test.py"
        case_id, case_no = case[0], case[1]
        uploader = session.execute(
            text("SELECT id FROM oa.sys_employee ORDER BY id LIMIT 1")
        ).scalar()
        print(f"[1] 使用 case_id={case_id} case_no={case_no} uploader={uploader}")

        # 2. 上传
        aid = attachment_service.upload(
            session,
            file_data=CONTENT, filename=FILENAME, biz_type=BIZ_TYPE, biz_id=case_id,
            category=CATEGORY, uploaded_by=uploader,
            entity_type=ENTITY_TYPE, entity_id=case_id, file_usage=FILE_USAGE,
        )
        session.commit()
        print(f"[2] upload → attachment_id={aid}")

        # 3. 校验 sys_attachment 字段
        att = session.get(SysAttachment, aid)
        year = datetime.now(timezone.utc).year
        assert att.bucket == "law-firm-files", f"bucket={att.bucket}"
        assert att.storage_type == "minio", f"storage_type={att.storage_type}"
        assert att.file_size == len(CONTENT), f"file_size={att.file_size}"
        assert att.object_key and att.object_key.startswith(f"cases/{year}/"), att.object_key
        assert case_no in att.object_key, f"object_key 未含 case_no: {att.object_key}"
        assert att.etag, "etag 为空"
        assert att.original_file_name == FILENAME
        print(f"[3] ✅ bucket={att.bucket} storage_type={att.storage_type}")
        print(f"      object_key={att.object_key}")
        print(f"      etag={att.etag} size={att.file_size}")

        # 4. MinIO 对象存在
        assert minio_service.file_exists(att.object_key), "MinIO 对象应存在"
        print("[4] ✅ MinIO 对象存在")

        # 5. 下载一致
        data = attachment_service.download(session, aid)
        assert data == CONTENT, f"下载不一致: {len(data)} vs {len(CONTENT)}"
        print(f"[5] ✅ 下载内容一致 ({len(data)} bytes)")

        # 6. 预签名 URL
        url = attachment_service.get_presigned_url(session, aid)
        assert url and "law-firm-files" in url, f"url={url}"
        print(f"[6] ✅ 预签名 URL: {url[:90]}...")

        # 7. relation
        rel = session.execute(
            text("SELECT entity_type, entity_id, file_usage FROM oa.sys_attachment_relation WHERE attachment_id=:a"),
            {"a": aid},
        ).first()
        assert rel and rel[0] == ENTITY_TYPE and rel[1] == case_id and rel[2] == FILE_USAGE, f"rel={rel}"
        print(f"[7] ✅ relation: entity_type={rel[0]} entity_id={rel[1]} file_usage={rel[2]}")

        # 8. 删除（软删 + MinIO 删）
        attachment_service.delete(session, aid, soft=True)
        session.commit()
        assert not minio_service.file_exists(att.object_key), "删除后 MinIO 对象应不存在"
        att2 = session.get(SysAttachment, aid)
        assert att2.deleted_at is not None, "软删标记应已设置"
        print(f"[8] ✅ 已删除（软删 sys_attachment + 删 MinIO 对象）")

        print("\n=== attachment_service 端到端验证通过 ===")


if __name__ == "__main__":
    main()
