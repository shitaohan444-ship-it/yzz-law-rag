from __future__ import annotations

import json
from pathlib import Path

from law_rag_bulk.reporting import write_reports
from law_rag_bulk.scanner import ScanEntry
from law_rag_bulk.storage import StateStore


def test_writes_utf8_json_and_excel_friendly_csv(tmp_path: Path) -> None:
    scan = ScanEntry("民法典.docx", "C:/民法典.docx", "民法典", 10, 20, "f" * 64, "ready")
    with StateStore(tmp_path / "state") as store:
        job_id = store.create_job(
            name="报告",
            source_root=tmp_path,
            category_id="2",
            category_name="法律",
            category_path=["法律"],
            api_url="http://api",
            entries=[scan],
        )
        json_path, csv_path = write_reports(store, job_id, tmp_path / "reports")
    assert json.loads(json_path.read_text(encoding="utf-8"))["files"][0]["title"] == "民法典"
    assert csv_path.read_bytes().startswith(b"\xef\xbb\xbf")
