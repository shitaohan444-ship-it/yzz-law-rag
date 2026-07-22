from __future__ import annotations

from pathlib import Path

from conftest import make_docx

from law_rag_bulk.scanner import scan_docx


def test_scans_only_valid_docx_and_records_invalid_or_temporary(tmp_path: Path) -> None:
    make_docx(tmp_path / "中文 目录" / "中华人民共和国民法典.docx")
    make_docx(tmp_path / "~$编辑中.docx")
    (tmp_path / "损坏.docx").write_text("not a zip", encoding="utf-8")
    (tmp_path / "忽略.txt").write_text("text", encoding="utf-8")

    entries = scan_docx(tmp_path, workers=2)

    assert [entry.relative_path for entry in entries] == [
        "~$编辑中.docx",
        "中文 目录/中华人民共和国民法典.docx",
        "损坏.docx",
    ]
    by_name = {entry.relative_path: entry for entry in entries}
    assert by_name["中文 目录/中华人民共和国民法典.docx"].status == "ready"
    assert len(by_name["中文 目录/中华人民共和国民法典.docx"].sha256 or "") == 64
    assert by_name["~$编辑中.docx"].status == "invalid"
    assert by_name["损坏.docx"].status == "invalid"


def test_hidden_directories_are_not_scanned(tmp_path: Path) -> None:
    make_docx(tmp_path / ".cache" / "hidden.docx")
    make_docx(tmp_path / "visible.docx")

    assert [entry.relative_path for entry in scan_docx(tmp_path)] == ["visible.docx"]
