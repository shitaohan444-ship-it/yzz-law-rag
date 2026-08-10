from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.legal_regulation_import import (
    CatalogEntry,
    CatalogValidationError,
    ImportReport,
    KnowledgeDocument,
    OfficialMetadataError,
    choose_latest,
    execute_import,
    normalize_category,
    normalize_title,
    parse_document_ids,
    propose_links,
    read_catalog,
    validate_official_url,
)


HEADER = "分类,法规名称,官网详情页,法规ID\n"
ID1 = "0123456789abcdef0123456789abcdef"
ID2 = "fedcba9876543210fedcba9876543210"


def row(category: str, name: str, external_id: str) -> str:
    return (
        f"{category},{name},https://flk.npc.gov.cn/detail?id={external_id},"
        f"{external_id}\n"
    )


class CatalogValidationTests(unittest.TestCase):
    def _write(self, directory: Path, body: str, encoding: str = "utf-8") -> Path:
        path = directory / "catalog.csv"
        path.write_bytes(body.encode(encoding))
        return path

    def test_reads_utf8_and_normalizes_explicit_category_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self._write(Path(temp), HEADER + row("地方法规", "某条例", ID1))
            entries, digest = read_catalog(path)
        self.assertEqual(entries[0].category, "地方性法规")
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_accepts_only_empty_excel_export_tail_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            body = (
                "分类,法规名称,官网详情页,法规ID,,\n"
                + row("法律", "某法律", ID1).rstrip("\n")
                + ",,\n"
            )
            entries, _ = read_catalog(self._write(Path(temp), body))
            self.assertEqual(len(entries), 1)
        with tempfile.TemporaryDirectory() as temp:
            body = (
                "分类,法规名称,官网详情页,法规ID,额外字段\n"
                + row("法律", "某法律", ID1).rstrip("\n")
                + ",unexpected\n"
            )
            with self.assertRaises(CatalogValidationError):
                read_catalog(self._write(Path(temp), body))

    def test_rejects_non_utf8_and_missing_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self._write(Path(temp), "分类,法规名称\n法律,民法典\n", "gbk")
            with self.assertRaises(CatalogValidationError):
                read_catalog(path)
        with tempfile.TemporaryDirectory() as temp:
            path = self._write(Path(temp), "分类,法规名称\n法律,民法典\n")
            with self.assertRaises(CatalogValidationError):
                read_catalog(path)

    def test_rejects_http_other_domains_and_id_mismatch(self) -> None:
        with self.assertRaises(CatalogValidationError):
            validate_official_url(f"http://flk.npc.gov.cn/detail?id={ID1}", ID1)
        with self.assertRaises(CatalogValidationError):
            validate_official_url(f"https://example.com/detail?id={ID1}", ID1)
        with self.assertRaises(CatalogValidationError):
            validate_official_url(f"https://flk.npc.gov.cn/detail?id={ID1}", ID2)
        with self.assertRaises(CatalogValidationError):
            validate_official_url("javascript:alert(1)", ID1)

    def test_rejects_duplicate_url_and_external_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self._write(
                Path(temp),
                HEADER + row("法律", "法规一", ID1) + row("法律", "法规二", ID1),
            )
            with self.assertRaises(CatalogValidationError):
                read_catalog(path)

    def test_title_normalization_handles_nfkc_prefix_punctuation_and_copy(self) -> None:
        normalized, copy_suffix = normalize_title("（已记录）某＿法规（试行）(2).PDF")
        self.assertEqual(normalized, "某法规试行")
        self.assertTrue(copy_suffix)
        self.assertEqual(normalize_category("地方法规"), "地方性法规")

    def test_document_id_list_accepts_inline_or_file_and_rejects_invalid(self) -> None:
        self.assertEqual(parse_document_ids("3, 2 3"), [2, 3])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ids.txt"
            path.write_text("5\n7", encoding="utf-8")
            self.assertEqual(parse_document_ids(str(path)), [5, 7])
        with self.assertRaises(CatalogValidationError):
            parse_document_ids("0,admin")


class MatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = ImportReport(
            provider="npc_flk",
            source_file="catalog.csv",
            source_sha256="a" * 64,
            mode="dry-run",
            generated_at="2026-07-31T00:00:00+00:00",
        )

    def test_unique_candidate_and_copy_suffix_match(self) -> None:
        entry = CatalogEntry(
            category="法律",
            name="某法律",
            normalized_name="某法律",
            official_url=f"https://flk.npc.gov.cn/detail?id={ID1}",
            external_id=ID1,
        )
        docs = [
            KnowledgeDocument(1, "某法律.pdf", "某法律", "法律", False),
            KnowledgeDocument(2, "某法律(2).pdf", "某法律", "法律", True),
        ]
        links = propose_links([entry], docs, set(), self.report)
        self.assertEqual([link.external_id for link in links], [ID1, ID1])
        self.assertEqual(
            [link.match_method for link in links],
            ["normalized_title", "copy_suffix"],
        )

    def test_same_name_versions_choose_latest_dates(self) -> None:
        older = CatalogEntry(
            "地方性法规",
            "某条例",
            "某条例",
            f"https://flk.npc.gov.cn/detail?id={ID1}",
            ID1,
            promulgation_date=date(2022, 1, 1),
            effective_date=date(2022, 2, 1),
        )
        newer = CatalogEntry(
            "地方性法规",
            "某条例",
            "某条例",
            f"https://flk.npc.gov.cn/detail?id={ID2}",
            ID2,
            promulgation_date=date(2025, 1, 1),
            effective_date=date(2025, 2, 1),
        )
        self.assertIs(choose_latest([older, newer]), newer)

    def test_equal_dates_and_metadata_failure_do_not_guess(self) -> None:
        first = CatalogEntry(
            "法律", "同名法", "同名法", f"https://flk.npc.gov.cn/detail?id={ID1}", ID1,
            promulgation_date=date(2025, 1, 1),
        )
        second = CatalogEntry(
            "法律", "同名法", "同名法", f"https://flk.npc.gov.cn/detail?id={ID2}", ID2,
            promulgation_date=date(2025, 1, 1),
        )
        self.assertIsNone(choose_latest([first, second]))
        self.assertIsNone(choose_latest([first, second], unresolved=True))

    def test_category_must_match(self) -> None:
        entry = CatalogEntry(
            "法律", "某条例", "某条例", f"https://flk.npc.gov.cn/detail?id={ID1}", ID1
        )
        doc = KnowledgeDocument(1, "某条例", "某条例", "行政法规", False)
        links = propose_links([entry], [doc], set(), self.report)
        self.assertEqual(links, [])
        self.assertEqual(self.report.errors[0]["code"], "NO_CATALOG_CANDIDATE")


class DryRunTests(unittest.TestCase):
    def test_dry_run_writes_report_but_never_calls_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            csv_path = root / "catalog.csv"
            csv_path.write_text(HEADER + row("法律", "某法律", ID1), encoding="utf-8")
            report_path = root / "report.json"
            connection = MagicMock()
            engine = MagicMock()
            engine.connect.return_value.__enter__.return_value = connection
            document = KnowledgeDocument(1, "某法律.pdf", "某法律", "法律", False)
            with (
                patch(
                    "app.legal_regulation_import.load_documents",
                    return_value=[document],
                ),
                patch(
                    "app.legal_regulation_import._official_tables_exist",
                    return_value=False,
                ),
                patch("app.legal_regulation_import.apply_import") as apply_mock,
            ):
                report = execute_import(
                    csv_path=csv_path,
                    report_path=report_path,
                    apply=False,
                    document_ids=None,
                    deactivate_missing=False,
                    engine=engine,
                )
            apply_mock.assert_not_called()
            self.assertEqual(report.statistics["links_proposed"], 1)
            self.assertEqual(json.loads(report_path.read_text("utf-8"))["mode"], "dry-run")


if __name__ == "__main__":
    unittest.main()
