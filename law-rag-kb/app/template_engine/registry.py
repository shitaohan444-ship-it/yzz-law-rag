from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.template_engine.compiler import inspect_template


def audit_registry(root: str | Path) -> dict:
    template_root = Path(root)
    reports = [inspect_template(path) for path in sorted(template_root.rglob("*.docx"))]
    formats = Counter(str(report["source_format"]) for report in reports)
    table_distribution = Counter(
        int(report["table_count"])
        for report in reports
        if report["source_format"] == "ooxml"
    )
    return {
        "template_count": len(reports),
        "format_distribution": dict(sorted(formats.items())),
        "table_distribution": dict(sorted(table_distribution.items())),
        "templates": reports,
    }
