"""离线/真实 Qwen VL 标注集评估（图片和 manifest 不应提交敏感案件数据）。

manifest JSON:
{
  "items": [
    {"file": "logo-01.png", "expected_keep": false,
     "expected_categories": ["decorative_logo", "watermark"], "critical": false}
  ]
}

用法：python scripts/eval_vl.py D:/secure/vl-eval/manifest.json
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ingest import parser, vl  # noqa: E402


def main() -> int:
    args = _parse_args()
    manifest_path = Path(args.manifest).resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    if len(items) < 30 and not args.allow_small:
        print(f"ERROR: acceptance manifest needs at least 30 items, got {len(items)}")
        return 2

    rows = []
    for item in items[: args.limit or None]:
        path = (manifest_path.parent / item["file"]).resolve()
        parsed = parser.parse(path.read_bytes(), path.suffix)
        if len(parsed.images) != 1:
            print(f"ERROR: {item['file']} must resolve to one image, got {len(parsed.images)}")
            return 2
        result = vl.analyze(parsed.images[0], doc_title=path.stem)
        expected_keep = bool(item["expected_keep"])
        expected_categories = set(item.get("expected_categories") or [])
        rows.append(
            {
                "file": item["file"],
                "expected_keep": expected_keep,
                "predicted_keep": result.keep_for_rag,
                "category_ok": not expected_categories or result.category in expected_categories,
                "critical": bool(item.get("critical", expected_keep)),
                "description_usable": (not expected_keep) or len(result.searchable_text) >= 10,
            }
        )
        print(
            f"{item['file']}: category={result.category} keep={result.keep_for_rag} "
            f"confidence={result.confidence:.2f}"
        )

    important = [row for row in rows if row["expected_keep"]]
    decorative = [row for row in rows if not row["expected_keep"]]
    predicted_filtered = [row for row in rows if not row["predicted_keep"]]
    critical_false_filters = sum(
        row["critical"] and not row["predicted_keep"] for row in rows
    )
    decorative_recall = _ratio(
        sum(not row["predicted_keep"] for row in decorative), len(decorative)
    )
    filtered_precision = _ratio(
        sum(not row["expected_keep"] for row in predicted_filtered),
        len(predicted_filtered),
    )
    description_usable = _ratio(
        sum(row["description_usable"] for row in important), len(important)
    )
    summary = {
        "total": len(rows),
        "critical_false_filters": critical_false_filters,
        "decorative_recall": round(decorative_recall, 4),
        "filtered_precision": round(filtered_precision, 4),
        "description_usable": round(description_usable, 4),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    passed = (
        critical_false_filters == 0
        and decorative_recall >= 0.90
        and filtered_precision >= 0.95
        and description_usable >= 0.90
    )
    return 0 if passed else 1


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _parse_args():
    parser_ = argparse.ArgumentParser()
    parser_.add_argument("manifest")
    parser_.add_argument("--limit", type=int, default=0)
    parser_.add_argument(
        "--allow-small", action="store_true", help="仅冒烟时允许少于30张；正式验收禁用"
    )
    return parser_.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
