from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import zipfile

import fitz
from PIL import Image

from app.drafting_lite import evidence_package
from app.drafting_lite.service import _validate_upload_content
from app.drafting_lite.evidence_directory import (
    EvidenceDirectoryResult,
    EvidenceItem,
    EvidenceSourceRef,
)


def _pdf(page_count: int = 3) -> bytes:
    document = fitz.open()
    try:
        for index in range(page_count):
            page = document.new_page()
            page.insert_text((72, 72), f"evidence page {index + 1}")
        return document.tobytes()
    finally:
        document.close()


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (20, 10), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _item(sequence: int, name: str, refs: list[EvidenceSourceRef]) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"ev-{sequence}",
        sequence=sequence,
        name=name,
        proof_purpose="证明案件事实",
        source_refs=refs,
        extraction_method="test",
    )


def test_package_orders_items_extracts_pdf_pages_and_keeps_images(tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    input_root = jobs_root / "job-1" / "input"
    output_root = jobs_root / "job-1" / "output"
    input_root.mkdir(parents=True)
    output_root.mkdir()
    pdf = _pdf()
    image = _png()
    (input_root / "01.pdf").write_bytes(pdf)
    (input_root / "02.png").write_bytes(image)
    directory = output_root / "证据目录.docx"
    directory.write_bytes(b"directory-docx")
    manifest = [
        {
            "source_kind": "upload",
            "name": "合并材料.pdf",
            "stored_name": "01.pdf",
            "size": len(pdf),
            "sha256": evidence_package._sha256(pdf),
            "mime_type": "application/pdf",
        },
        {
            "source_kind": "upload",
            "name": "付款截图.png",
            "stored_name": "02.png",
            "size": len(image),
            "sha256": evidence_package._sha256(image),
            "mime_type": "image/png",
        },
    ]
    result = EvidenceDirectoryResult(
        status="generated",
        items=[
            _item(
                1,
                "借款合同",
                [
                    EvidenceSourceRef(
                        material_id=1,
                        source_kind="upload",
                        file_name="合并材料.pdf",
                        stored_name="01.pdf",
                        page_no=2,
                    )
                ],
            ),
            _item(
                2,
                "付款截图",
                [
                    EvidenceSourceRef(
                        material_id=2,
                        source_kind="upload",
                        file_name="付款截图.png",
                        stored_name="02.png",
                        page_no=1,
                    )
                ],
            ),
        ],
    )

    output, filename, package_result, audit = evidence_package.render_evidence_package(
        "job-1",
        "民间借贷纠纷",
        "张三",
        result,
        directory,
        manifest,
        jobs_root,
    )

    assert filename == "民间借贷纠纷_张三_证据材料包.zip"
    assert package_result.status == "generated"
    assert audit.is_file()
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert names[0] == "000_证据目录.docx"
        pdf_name = next(name for name in names if name.endswith(".pdf"))
        image_name = next(name for name in names if name.endswith(".png"))
        assert pdf_name.startswith("001_证据一_借款合同/001-01_")
        assert image_name.startswith("002_证据二_付款截图/002-01_")
        subset = fitz.open(stream=archive.read(pdf_name), filetype="pdf")
        try:
            assert subset.page_count == 1
            assert "evidence page 2" in subset[0].get_text()
        finally:
            subset.close()
        assert archive.read(image_name) == image
        index = json.loads(archive.read("证据材料索引.json"))
        assert [item["sequence"] for item in index["items"]] == [1, 2]


def test_missing_original_creates_explanation_and_partial_package(tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    output_root = jobs_root / "job-2" / "output"
    (jobs_root / "job-2" / "input").mkdir(parents=True)
    output_root.mkdir()
    directory = output_root / "证据目录.docx"
    directory.write_bytes(b"directory-docx")
    result = EvidenceDirectoryResult(
        status="generated",
        items=[
            _item(
                1,
                "转账记录",
                [
                    EvidenceSourceRef(
                        material_id=1,
                        source_kind="upload",
                        file_name="不存在.pdf",
                        stored_name="missing.pdf",
                    )
                ],
            )
        ],
    )
    manifest = [
        {
            "source_kind": "upload",
            "name": "不存在.pdf",
            "stored_name": "missing.pdf",
            "size": 0,
            "sha256": "",
        }
    ]

    output, _, package_result, _ = evidence_package.render_evidence_package(
        "job-2", "买卖合同纠纷", "甲公司", result, directory, manifest, jobs_root
    )

    assert package_result.status == "partial"
    with zipfile.ZipFile(output) as archive:
        missing = next(name for name in archive.namelist() if name.endswith("缺失说明.txt"))
        text = archive.read(missing).decode("utf-8-sig")
        assert "上传原件不存在" in text
        assert "转账记录" in text


def test_knowledge_source_and_image_are_resolved_from_snapshot(monkeypatch, tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    input_root = jobs_root / "job-3" / "input"
    input_root.mkdir(parents=True)
    snapshot = {
        "snapshot_version": 2,
        "document_id": 9,
        "sources": [
            {
                "source_id": 12,
                "attachment_id": 20,
                "is_primary": True,
                "file_name": "合同.pdf",
                "mime_type": "application/pdf",
                "bucket": "law",
                "object_key": "contracts/20.pdf",
            }
        ],
        "images": [
            {
                "image_id": 31,
                "mime_type": "image/png",
                "bucket": "law",
                "object_key": "images/31.png",
            }
        ],
    }
    (input_root / "kb-9.json").write_text(json.dumps(snapshot), encoding="utf-8")
    manifest = [
        {
            "source_kind": "knowledge",
            "snapshot_name": "kb-9.json",
            "size": 10,
            "document_id": 9,
        }
    ]
    payloads = {"contracts/20.pdf": _pdf(1), "images/31.png": _png()}
    monkeypatch.setattr(
        evidence_package,
        "storage_download",
        lambda object_key, bucket: payloads[object_key],
    )
    registry = evidence_package._SourceRegistry("job-3", manifest, jobs_root)

    attachment = registry.resolve(
        EvidenceSourceRef(
            material_id=1,
            source_kind="knowledge_attachment",
            document_id=9,
            source_id=12,
            file_name="合同.pdf",
        )
    )
    image = registry.resolve(
        EvidenceSourceRef(
            material_id=1,
            source_kind="knowledge_image",
            document_id=9,
            image_id=31,
            file_name="合同图片.png",
        )
    )

    assert attachment.path.read_bytes().startswith(b"%PDF-")
    assert attachment.source_kind == "knowledge_attachment"
    assert image.path.read_bytes().startswith(b"\x89PNG")
    assert image.source_kind == "knowledge_image"


def test_upload_validation_accepts_images_and_rejects_mismatched_content():
    assert _validate_upload_content("付款截图.png", _png(), "image/png") == ".png"
    try:
        _validate_upload_content("伪造图片.png", b"%PDF-1.7", "image/png")
    except ValueError as exc:
        assert "内容与扩展名不一致" in str(exc)
    else:
        raise AssertionError("mismatched upload content should be rejected")
