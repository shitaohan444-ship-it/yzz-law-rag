#!/usr/bin/env python3
"""
MinIO 基础功能测试脚本

说明：
- 本脚本只验证 MinIO 基础设施与基础 service 是否可用，
  不涉及 file_object / case_material / kb_document 等业务表字段。
- category 使用业务分类（evidence / contract / consultation / agreement），
  而不是 pdf / word 文件格式。
- 运行前请确保 MinIO 已启动且 .env 配置正确。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 把 service 根目录加入 PYTHONPATH，使 app.services 可导入
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from minio.error import S3Error

from app.services.minio_service import MinIOService


TEST_FILES_DIR = Path(ROOT.parent, "test_files")  # law-rag-project/test_files
TEST_SAMPLES = {
    "case_evidence_pdf": "sample_test_upload.pdf",
    "case_contract_docx": "sample_test_upload.docx",
    "lead_consultation_pdf": "sample_test_upload.pdf",
    "contract_agreement_docx": "sample_test_upload.docx",
}


def ensure_test_files() -> dict[str, Path]:
    """如果 test_files 目录没有 PDF/Word，就自动生成两个示例文件。"""
    TEST_FILES_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    # PDF: 最简单的有效 PDF（仅头尾，无实际页面内容，但 mime 正确）
    pdf_path = TEST_FILES_DIR / TEST_SAMPLES["case_evidence_pdf"]
    if not pdf_path.exists():
        pdf_path.write_bytes(
            b"%PDF-1.4\n1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj\n"
            b"2 0 obj\n<</Type /Pages /Kids [] /Count 0>>\nendobj\n"
            b"xref\n0 3\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n"
            b"trailer\n<</Size 3 /Root 1 0 R>>\nstartxref\n109\n%%EOF\n"
        )
    paths["case_evidence_pdf"] = pdf_path
    paths["lead_consultation_pdf"] = pdf_path

    # DOCX: 最小有效 docx（ZIP 结构）
    docx_path = TEST_FILES_DIR / TEST_SAMPLES["case_contract_docx"]
    if not docx_path.exists():
        import zipfile

        with zipfile.ZipFile(docx_path, "w") as zf:
            zf.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>",
            )
            zf.writestr(
                "_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="word/document.xml"/>'
                "</Relationships>",
            )
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>MinIO 测试 Word 文件</w:t></w:r></w:p></w:body>"
                "</w:document>",
            )
    paths["case_contract_docx"] = docx_path
    paths["contract_agreement_docx"] = docx_path

    return paths


def validate_object_key(pattern_name: str, object_key: str, expected_prefix: str) -> None:
    """校验 object_key 是否符合规则。"""
    assert object_key.startswith(expected_prefix), (
        f"{pattern_name} object_key 前缀不匹配: {object_key}"
    )
    # 校验 timestamp_uuid8_filename 结构
    filename = Path(object_key).name
    assert re.match(r"^\d{14}_[0-9a-f]{8}_.+$", filename), (
        f"{pattern_name} 文件名部分不符合 {{yyyyMMddHHmmss}}_{{uuid8}}_{{filename}} 规则: {filename}"
    )


def main() -> None:
    print("=" * 70)
    print("MinIO 基础功能测试")
    print("=" * 70)

    service = MinIOService()

    # 1. 确保 bucket 存在
    bucket = service.ensure_bucket()
    print(f"[1] Bucket 确认: {bucket}")

    # 2. 当前 bucket 列表
    print("\n[2] 当前 MinIO bucket 列表:")
    for b in service.client.list_buckets():
        print(f"    - {b.name}")

    # 3. 准备测试文件
    sample_paths = ensure_test_files()
    print("\n[3] 测试文件准备完成:")
    for name, path in sample_paths.items():
        print(f"    - {name}: {path}")

    # 4. 生成并校验 object_key
    test_cases = [
        {
            "name": "案件证据文件",
            "prefix": "cases",
            "path_key": "case_evidence_pdf",
            "year": 2026,
            "month": 7,
            "entity_no": "CASE-2026-07001",
            "category": "evidence",
            "expected_prefix": "cases/2026/07/CASE-2026-07001/evidence/",
        },
        {
            "name": "案件合同文件",
            "prefix": "cases",
            "path_key": "case_contract_docx",
            "year": 2026,
            "month": 7,
            "entity_no": "CASE-2026-07001",
            "category": "contract",
            "expected_prefix": "cases/2026/07/CASE-2026-07001/contract/",
        },
        {
            "name": "线索咨询文件",
            "prefix": "leads",
            "path_key": "lead_consultation_pdf",
            "year": 2026,
            "month": 7,
            "entity_no": "LEAD-2026-07001",
            "category": "consultation",
            "expected_prefix": "leads/2026/07/LEAD-2026-07001/consultation/",
        },
        {
            "name": "合同协议文件",
            "prefix": "contracts",
            "path_key": "contract_agreement_docx",
            "year": 2026,
            "month": 7,
            "entity_no": "AGREE-2026-0001",
            "category": "agreement",
            "expected_prefix": "contracts/2026/07/AGREE-2026-0001/agreement/",
        },
    ]

    object_keys: dict[str, str] = {}
    print("\n[4] 生成 object_key:")
    for case in test_cases:
        key = service.build_object_key(
            case["prefix"],
            filename=sample_paths[case["path_key"]].name,
            year=case["year"],
            month=case["month"],
            entity_no=case["entity_no"],
            category=case["category"],
        )
        validate_object_key(case["name"], key, case["expected_prefix"])
        object_keys[case["name"]] = key
        print(f"    [{case['name']}] {key}")

    # 5. 上传
    upload_results: dict[str, dict] = {}
    print("\n[5] 上传文件:")
    for case in test_cases:
        key = object_keys[case["name"]]
        result = service.upload_file(key, sample_paths[case["path_key"]])
        upload_results[case["name"]] = result
        print(
            f"    [{case['name']}] 上传成功: bucket={result['bucket']}, "
            f"etag={result['etag']}, size={result['size']}"
        )

    # 6. 验证默认不允许覆盖
    print("\n[6] 验证默认禁止覆盖:")
    try:
        first_key = object_keys[test_cases[0]["name"]]
        service.upload_file(first_key, sample_paths[test_cases[0]["path_key"]])
        print("    [FAIL] 应该抛出 FileExistsError")
    except FileExistsError as exc:
        print(f"    [PASS] 成功阻止覆盖: {exc}")

    # 7. 检查对象是否存在
    print("\n[7] 检查对象是否存在:")
    for case in test_cases:
        exists = service.file_exists(object_keys[case["name"]])
        print(f"    [{case['name']}] exists={exists}")

    # 8. 生成预签名下载链接
    print("\n[8] 生成预签名下载链接:")
    for case in test_cases:
        url = service.get_presigned_url(
            object_keys[case["name"]], expires=3600, method="GET"
        )
        print(f"    [{case['name']}] {url[:120]}...")

    # 9. 下载并校验大小
    print("\n[9] 下载并校验大小:")
    for case in test_cases:
        key = object_keys[case["name"]]
        content = service.download_file(key)
        expected_size = sample_paths[case["path_key"]].stat().st_size
        match = len(content) == expected_size
        print(
            f"    [{case['name']}] size={len(content)}, expected={expected_size}, "
            f"match={match}"
        )

    # 10. 删除（清理）
    print("\n[10] 删除测试对象:")
    for case in test_cases:
        key = object_keys[case["name"]]
        service.delete_file(key)
        exists = service.file_exists(key)
        print(f"    [{case['name']}] 已删除, exists={exists}")

    # 11. 临时文件规则示例
    temp_key = service.build_object_key("temp", filename="draft.txt", temp=True)
    print(f"\n[11] temp object_key 示例: {temp_key}")

    print("\n" + "=" * 70)
    print("测试完成，所有步骤通过")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except S3Error as exc:
        print(f"\nMinIO 错误: {exc}")
        raise
    except Exception as exc:
        print(f"\n测试失败: {exc}")
        raise
