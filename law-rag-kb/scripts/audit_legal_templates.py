from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.template_engine import compile_template, load_schema
from app.template_engine.registry import audit_registry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--normalized-root", required=True)
    args = parser.parse_args()

    template_root = Path(args.template_root).resolve()
    output_root = Path(args.output_root).resolve()
    normalized_root = Path(args.normalized_root).resolve()
    report = audit_registry(template_root)
    for item in report["templates"]:
        item["relative_path"] = str(Path(item["path"]).resolve().relative_to(template_root)).replace("\\", "/")
        item.pop("path", None)

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "template-inventory.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_root / "template-inventory.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "relative_path", "sha256", "file_size", "source_format", "table_count",
            "content_control_count", "bookmark_count", "merge_marker_count", "checkbox_symbol_count",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({key: item.get(key) for key in fieldnames} for item in report["templates"])

    schema_root = PROJECT_ROOT / "app" / "template_engine" / "schemas"
    for schema_name, report_name in (
        ("private_lending_complaint.v1.json", "private-lending-compiler-report.json"),
        ("trademark_defense.v1.json", "trademark-defense-compiler-report.json"),
    ):
        schema = load_schema(schema_root / schema_name)
        normalized = normalized_root / schema.source_path
        compiler_report = compile_template(
            template_root / schema.source_path, normalized, schema
        )
        (output_root / report_name).write_text(
            json.dumps(compiler_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if report["template_count"] != 113:
        raise SystemExit(f"expected 113 templates, got {report['template_count']}")
    if report["format_distribution"] != {"ole_doc": 2, "ooxml": 111}:
        raise SystemExit(f"unexpected format distribution: {report['format_distribution']}")


if __name__ == "__main__":
    main()
