#!/usr/bin/env python3
"""CLI wrapper for the NPC official regulation catalog importer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Direct execution from the migration image sets sys.path to /app/scripts.
# Add the image/project root so ``app`` resolves without depending on cwd.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.legal_regulation_import import (
    CatalogValidationError,
    execute_import,
    parse_document_ids,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import NPC official regulation links without touching RAG data."
    )
    parser.add_argument("--csv", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--document-ids",
        help="Comma/whitespace separated positive IDs, or a UTF-8 file containing them.",
    )
    parser.add_argument("--deactivate-missing", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = execute_import(
            csv_path=args.csv.resolve(),
            report_path=args.report.resolve(),
            apply=args.apply,
            document_ids=parse_document_ids(args.document_ids),
            deactivate_missing=args.deactivate_missing,
        )
    except (CatalogValidationError, OSError, RuntimeError) as exc:
        print(
            json.dumps(
                {"status": "failed", "error_code": type(exc).__name__},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "status": "completed",
                "mode": report.mode,
                "source_sha256": report.source_sha256,
                "statistics": report.statistics,
                "error_count": len(report.errors),
                "report": str(args.report.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
