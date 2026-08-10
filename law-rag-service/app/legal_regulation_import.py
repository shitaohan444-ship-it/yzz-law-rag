"""Repeatable import of NPC official legal-regulation links.

The module intentionally never reads or writes MinIO/Milvus and never invokes
the document-ingest API.  Database writes are limited to the three additive
official-link tables created by migration b4c5d6e7f8a9.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import Request, urlopen

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Connection, Engine

PROVIDER = "npc_flk"
SOURCE_NAME = "国家法律法规数据库"
EXPECTED_HEADERS = ("分类", "法规名称", "官网详情页", "法规ID")
EXTERNAL_ID_RE = re.compile(r"^[0-9a-f]{32}$")
ALLOWED_HOST = "flk.npc.gov.cn"
DETAIL_PATH = "/detail"
METADATA_URL = "https://flk.npc.gov.cn/law-search/search/flfgDetails?bbbs={external_id}"
USER_AGENT = "LawFirmOfficialLinkImporter/1.0 (+offline-catalog-maintenance)"
REFERER = "https://flk.npc.gov.cn/"
ROOT_CATEGORY = "法律法规"
CATEGORY_ALIASES = {
    "地方法规": "地方性法规",
    "地方性法规": "地方性法规",
}
_FILE_EXTENSION_RE = re.compile(
    r"\.(?:pdf|docx?|txt|rtf|odt|wps|md|html?)$", re.IGNORECASE
)
_OPERATION_PREFIX_RE = re.compile(r"^[（(]\s*(?:已记录|已入库)\s*[）)]\s*")
_COPY_SUFFIX_RE = re.compile(r"\s*[（(]\s*2\s*[）)]\s*$")


class CatalogValidationError(ValueError):
    """Raised when the CSV itself is not safe to import."""


class OfficialMetadataError(RuntimeError):
    """Raised when official metadata is unavailable or inconsistent."""


@dataclass
class CatalogEntry:
    category: str
    name: str
    normalized_name: str
    official_url: str
    external_id: str
    promulgation_date: date | None = None
    effective_date: date | None = None
    effectivity_status: str | None = None
    issuing_authority: str | None = None
    verified_at: datetime | None = None


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: int
    title: str
    normalized_name: str
    category: str
    used_copy_suffix: bool


@dataclass(frozen=True)
class ProposedLink:
    document_id: int
    external_id: str
    match_method: str


@dataclass
class ImportReport:
    provider: str
    source_file: str
    source_sha256: str
    mode: str
    generated_at: str
    statistics: dict[str, int] = field(default_factory=dict)
    errors: list[dict[str, object]] = field(default_factory=list)
    warnings: list[dict[str, object]] = field(default_factory=list)
    selected_document_ids: list[int] | None = None

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_category(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").strip()
    return CATEGORY_ALIASES.get(normalized, normalized)


def normalize_title(value: str) -> tuple[str, bool]:
    """Return a stable matching key and whether a ``(2)`` copy suffix existed."""
    normalized = unicodedata.normalize("NFKC", value or "").strip()
    normalized = _FILE_EXTENSION_RE.sub("", normalized).strip()
    normalized = _OPERATION_PREFIX_RE.sub("", normalized).strip()
    copy_match = bool(_COPY_SUFFIX_RE.search(normalized))
    normalized = _COPY_SUFFIX_RE.sub("", normalized).strip()
    normalized = "".join(
        char
        for char in normalized
        if unicodedata.category(char)[0] not in {"P", "S", "Z"}
        and char != "_"
    )
    return normalized.casefold(), copy_match


def validate_official_url(url: str, external_id: str) -> str:
    if not EXTERNAL_ID_RE.fullmatch(external_id):
        raise CatalogValidationError("法规ID必须为32位小写十六进制")
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != ALLOWED_HOST
        or parsed.port is not None
        or parsed.path != DETAIL_PATH
        or parsed.fragment
    ):
        raise CatalogValidationError("官网URL必须为flk.npc.gov.cn的HTTPS详情页")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if set(query) != {"id"} or query["id"] != [external_id]:
        raise CatalogValidationError("官网URL中的法规ID与法规ID字段不一致")
    return f"https://{ALLOWED_HOST}{DETAIL_PATH}?id={external_id}"


def _read_csv_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CatalogValidationError("CSV必须使用UTF-8编码") from exc


def read_catalog(path: Path) -> tuple[list[CatalogEntry], str]:
    raw = path.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    try:
        text_value = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CatalogValidationError("CSV必须使用UTF-8编码") from exc

    reader = csv.reader(text_value.splitlines())
    try:
        raw_headers = next(reader)
    except StopIteration as exc:
        raise CatalogValidationError("CSV没有表头") from exc
    while raw_headers and not raw_headers[-1].strip():
        raw_headers.pop()
    if tuple(header.strip() for header in raw_headers) != EXPECTED_HEADERS:
        raise CatalogValidationError(
            f"CSV表头必须严格为：{','.join(EXPECTED_HEADERS)}"
        )

    entries: list[CatalogEntry] = []
    seen_urls: set[str] = set()
    seen_ids: set[str] = set()
    for line_no, raw_row in enumerate(reader, 2):
        while raw_row and not raw_row[-1].strip():
            raw_row.pop()
        if len(raw_row) != len(EXPECTED_HEADERS):
            raise CatalogValidationError(f"第{line_no}行存在非空额外字段或字段缺失")
        row = dict(zip(EXPECTED_HEADERS, raw_row, strict=True))
        category = normalize_category(row["分类"])
        name = unicodedata.normalize("NFKC", row["法规名称"]).strip()
        url = row["官网详情页"].strip()
        external_id = row["法规ID"].strip().lower()
        if not category or not name or not url or not external_id:
            raise CatalogValidationError(f"第{line_no}行存在空值")
        safe_url = validate_official_url(url, external_id)
        normalized_name, _ = normalize_title(name)
        if not normalized_name:
            raise CatalogValidationError(f"第{line_no}行法规名称规范化后为空")
        if safe_url in seen_urls:
            raise CatalogValidationError(f"第{line_no}行官网URL重复")
        if external_id in seen_ids:
            raise CatalogValidationError(f"第{line_no}行法规ID重复")
        seen_urls.add(safe_url)
        seen_ids.add(external_id)
        entries.append(
            CatalogEntry(
                category=category,
                name=name,
                normalized_name=normalized_name,
                official_url=safe_url,
                external_id=external_id,
            )
        )
    if not entries:
        raise CatalogValidationError("CSV没有数据行")
    return entries, sha256


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw[:10].replace("/", "-")
    try:
        return date.fromisoformat(raw)
    except ValueError:
        compact = re.sub(r"\D", "", raw)
        if len(compact) == 8:
            return date(int(compact[:4]), int(compact[4:6]), int(compact[6:8]))
        raise OfficialMetadataError("官网日期格式无法识别")


class OfficialMetadataClient:
    def __init__(
        self,
        *,
        delay_seconds: float = 1.0,
        timeout_seconds: float = 15.0,
        retries: int = 2,
        opener: Callable[..., object] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.delay_seconds = max(1.0, delay_seconds)
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.opener = opener
        self.sleeper = sleeper
        self._last_request_at: float | None = None
        self._cache: dict[str, dict[str, object]] = {}

    def fetch(self, entry: CatalogEntry) -> dict[str, object]:
        cached = self._cache.get(entry.external_id)
        if cached is not None:
            return cached
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            if self._last_request_at is not None:
                elapsed = time.monotonic() - self._last_request_at
                if elapsed < self.delay_seconds:
                    self.sleeper(self.delay_seconds - elapsed)
            request = Request(
                METADATA_URL.format(external_id=entry.external_id),
                headers={"User-Agent": USER_AGENT, "Referer": REFERER},
                method="GET",
            )
            try:
                with self.opener(request, timeout=self.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                self._last_request_at = time.monotonic()
                if str(payload.get("code")) != "200":
                    raise OfficialMetadataError("官网元数据接口返回非成功状态")
                data = payload.get("data")
                if not isinstance(data, dict):
                    raise OfficialMetadataError("官网元数据缺少data对象")
                if str(data.get("bbbs", "")).lower() != entry.external_id:
                    raise OfficialMetadataError("官网元数据法规ID不一致")
                official_title, _ = normalize_title(str(data.get("title", "")))
                if official_title != entry.normalized_name:
                    raise OfficialMetadataError("官网元数据标题不一致")
                result: dict[str, object] = {
                    "promulgation_date": _parse_date(data.get("gbrq")),
                    "effective_date": _parse_date(data.get("sxrq")),
                    "effectivity_status": str(data.get("sxx") or "").strip() or None,
                    "issuing_authority": str(data.get("zdjgName") or "").strip()
                    or None,
                }
                self._cache[entry.external_id] = result
                return result
            except (
                HTTPError,
                URLError,
                TimeoutError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                OfficialMetadataError,
            ) as exc:
                self._last_request_at = time.monotonic()
                last_error = exc
                if attempt < self.retries:
                    continue
        raise OfficialMetadataError(
            f"官网元数据获取失败：{type(last_error).__name__}"
        ) from last_error


def enrich_duplicate_metadata(
    entries: Sequence[CatalogEntry],
    client: OfficialMetadataClient,
    report: ImportReport,
) -> set[tuple[str, str]]:
    grouped: dict[tuple[str, str], list[CatalogEntry]] = defaultdict(list)
    for entry in entries:
        grouped[(entry.category, entry.normalized_name)].append(entry)
    unresolved: set[tuple[str, str]] = set()
    duplicate_groups = [key for key, values in grouped.items() if len(values) > 1]
    report.statistics["duplicate_catalog_groups"] = len(duplicate_groups)
    report.statistics["metadata_requests"] = sum(len(grouped[key]) for key in duplicate_groups)
    for key in duplicate_groups:
        group_failed = False
        for entry in grouped[key]:
            try:
                metadata = client.fetch(entry)
                entry.promulgation_date = metadata["promulgation_date"]  # type: ignore[assignment]
                entry.effective_date = metadata["effective_date"]  # type: ignore[assignment]
                entry.effectivity_status = metadata["effectivity_status"]  # type: ignore[assignment]
                entry.issuing_authority = metadata["issuing_authority"]  # type: ignore[assignment]
                entry.verified_at = datetime.now(timezone.utc)
            except OfficialMetadataError as exc:
                group_failed = True
                report.errors.append(
                    {
                        "code": "OFFICIAL_METADATA_FAILED",
                        "external_id": entry.external_id,
                        "message": str(exc),
                    }
                )
        if group_failed:
            unresolved.add(key)
    report.statistics["metadata_failed_groups"] = len(unresolved)
    return unresolved


def choose_latest(
    candidates: Sequence[CatalogEntry],
    *,
    unresolved: bool = False,
) -> CatalogEntry | None:
    if len(candidates) == 1:
        return candidates[0]
    if unresolved or any(item.promulgation_date is None for item in candidates):
        return None
    ranked = sorted(
        candidates,
        key=lambda item: (
            item.promulgation_date or date.min,
            item.effective_date or date.min,
        ),
        reverse=True,
    )
    best_key = (ranked[0].promulgation_date, ranked[0].effective_date)
    runner_up_key = (ranked[1].promulgation_date, ranked[1].effective_date)
    return None if best_key == runner_up_key else ranked[0]


_DOCUMENT_SQL = text(
    """
    WITH RECURSIVE category_paths AS (
      SELECT c.id, c.parent_id, ARRAY[c.category_name]::text[] AS path
      FROM oa.kb_category c
      WHERE c.parent_id IS NULL AND c.deleted_at IS NULL
      UNION ALL
      SELECT child.id, child.parent_id, parent.path || child.category_name
      FROM oa.kb_category child
      JOIN category_paths parent ON child.parent_id = parent.id
      WHERE child.deleted_at IS NULL
    )
    SELECT d.id AS document_id, d.doc_title,
           CASE WHEN cardinality(cp.path) >= 2 THEN cp.path[2] ELSE cp.path[1] END
             AS regulation_category
    FROM oa.kb_document d
    JOIN category_paths cp ON cp.id = d.category_id
    WHERE cp.path[1] = :root_category
      AND d.deleted_at IS NULL
      AND d.status IN ('active', 'staging')
      AND (:all_documents OR d.id IN :document_ids)
    ORDER BY d.id
    """
).bindparams(bindparam("document_ids", expanding=True))


def load_documents(
    connection: Connection, document_ids: Sequence[int] | None
) -> list[KnowledgeDocument]:
    selected = sorted({int(value) for value in (document_ids or []) if int(value) > 0})
    rows = connection.execute(
        _DOCUMENT_SQL,
        {
            "root_category": ROOT_CATEGORY,
            "all_documents": not selected,
            "document_ids": selected or [-1],
        },
    ).mappings()
    documents: list[KnowledgeDocument] = []
    for row in rows:
        normalized_name, copy_suffix = normalize_title(str(row["doc_title"]))
        documents.append(
            KnowledgeDocument(
                document_id=int(row["document_id"]),
                title=str(row["doc_title"]),
                normalized_name=normalized_name,
                category=normalize_category(str(row["regulation_category"])),
                used_copy_suffix=copy_suffix,
            )
        )
    return documents


def propose_links(
    entries: Sequence[CatalogEntry],
    documents: Sequence[KnowledgeDocument],
    unresolved_groups: set[tuple[str, str]],
    report: ImportReport,
) -> list[ProposedLink]:
    candidates: dict[tuple[str, str], list[CatalogEntry]] = defaultdict(list)
    for entry in entries:
        candidates[(entry.category, entry.normalized_name)].append(entry)

    links: list[ProposedLink] = []
    for document in documents:
        key = (document.category, document.normalized_name)
        group = candidates.get(key, [])
        if not group:
            report.errors.append(
                {
                    "code": "NO_CATALOG_CANDIDATE",
                    "document_id": document.document_id,
                }
            )
            continue
        latest = choose_latest(group, unresolved=key in unresolved_groups)
        if latest is None:
            report.errors.append(
                {
                    "code": "LATEST_VERSION_UNRESOLVED",
                    "document_id": document.document_id,
                    "candidate_count": len(group),
                }
            )
            continue
        method = (
            "latest_by_date"
            if len(group) > 1
            else "copy_suffix"
            if document.used_copy_suffix
            else "normalized_title"
        )
        links.append(
            ProposedLink(
                document_id=document.document_id,
                external_id=latest.external_id,
                match_method=method,
            )
        )
    report.statistics["documents_considered"] = len(documents)
    report.statistics["links_proposed"] = len(links)
    report.statistics["documents_unresolved"] = len(documents) - len(links)
    return links


def _upsert_catalog(
    connection: Connection,
    entries: Sequence[CatalogEntry],
    run_id: int,
    deactivate_missing: bool,
) -> dict[str, int]:
    values = [
        {
            "provider": PROVIDER,
            "external_id": item.external_id,
            "regulation_name": item.name,
            "normalized_name": item.normalized_name,
            "regulation_category": item.category,
            "official_url": item.official_url,
            "promulgation_date": item.promulgation_date,
            "effective_date": item.effective_date,
            "effectivity_status": item.effectivity_status,
            "issuing_authority": item.issuing_authority,
            "verified_at": item.verified_at,
            "run_id": run_id,
        }
        for item in entries
    ]
    statement = text(
        """
        INSERT INTO oa.legal_regulation_catalog
          (provider, external_id, regulation_name, normalized_name,
           regulation_category, official_url, promulgation_date, effective_date,
           effectivity_status, issuing_authority, is_current, last_seen_run_id,
           verified_at)
        VALUES
          (:provider, :external_id, :regulation_name, :normalized_name,
           :regulation_category, :official_url, :promulgation_date, :effective_date,
           :effectivity_status, :issuing_authority, true, :run_id, :verified_at)
        ON CONFLICT (provider, external_id) DO UPDATE SET
          regulation_name = EXCLUDED.regulation_name,
          normalized_name = EXCLUDED.normalized_name,
          regulation_category = EXCLUDED.regulation_category,
          official_url = EXCLUDED.official_url,
          promulgation_date = COALESCE(EXCLUDED.promulgation_date,
                                      oa.legal_regulation_catalog.promulgation_date),
          effective_date = COALESCE(EXCLUDED.effective_date,
                                    oa.legal_regulation_catalog.effective_date),
          effectivity_status = COALESCE(EXCLUDED.effectivity_status,
                                        oa.legal_regulation_catalog.effectivity_status),
          issuing_authority = COALESCE(EXCLUDED.issuing_authority,
                                       oa.legal_regulation_catalog.issuing_authority),
          is_current = true,
          last_seen_run_id = EXCLUDED.last_seen_run_id,
          verified_at = COALESCE(EXCLUDED.verified_at,
                                 oa.legal_regulation_catalog.verified_at),
          updated_at = now()
        """
    )
    for offset in range(0, len(values), 500):
        connection.execute(statement, values[offset : offset + 500])
    if deactivate_missing:
        connection.execute(
            text(
                """
                UPDATE oa.legal_regulation_catalog
                SET is_current = false, updated_at = now()
                WHERE provider = :provider
                  AND last_seen_run_id IS DISTINCT FROM :run_id
                """
            ),
            {"provider": PROVIDER, "run_id": run_id},
        )
    rows = connection.execute(
        text(
            """
            SELECT external_id, id
            FROM oa.legal_regulation_catalog
            WHERE provider = :provider AND external_id = ANY(:external_ids)
            """
        ),
        {"provider": PROVIDER, "external_ids": [item.external_id for item in entries]},
    ).mappings()
    return {str(row["external_id"]): int(row["id"]) for row in rows}


def _upsert_links(
    connection: Connection,
    links: Sequence[ProposedLink],
    catalog_ids: dict[str, int],
    run_id: int,
) -> None:
    statement = text(
        """
        INSERT INTO oa.kb_document_regulation_link
          (document_id, catalog_id, match_method, version_semantics, linked_run_id)
        VALUES
          (:document_id, :catalog_id, :match_method,
           'latest_official_by_title', :run_id)
        ON CONFLICT (document_id) DO UPDATE SET
          catalog_id = EXCLUDED.catalog_id,
          match_method = EXCLUDED.match_method,
          version_semantics = EXCLUDED.version_semantics,
          linked_run_id = EXCLUDED.linked_run_id,
          updated_at = now()
        """
    )
    values = [
        {
            "document_id": link.document_id,
            "catalog_id": catalog_ids[link.external_id],
            "match_method": link.match_method,
            "run_id": run_id,
        }
        for link in links
    ]
    for offset in range(0, len(values), 500):
        connection.execute(statement, values[offset : offset + 500])


def apply_import(
    engine: Engine,
    entries: Sequence[CatalogEntry],
    links: Sequence[ProposedLink],
    report: ImportReport,
    *,
    deactivate_missing: bool,
) -> int:
    with engine.begin() as connection:
        run_id = int(
            connection.execute(
                text(
                    """
                    INSERT INTO oa.legal_regulation_import_run
                      (provider, source_filename, source_sha256, execution_mode,
                       status, statistics, report_summary)
                    VALUES
                      (:provider, :source_filename, :source_sha256, 'apply',
                       'running', CAST(:statistics AS jsonb),
                       CAST(:report_summary AS jsonb))
                    RETURNING id
                    """
                ),
                {
                    "provider": PROVIDER,
                    "source_filename": Path(report.source_file).name,
                    "source_sha256": report.source_sha256,
                    "statistics": json.dumps(report.statistics, ensure_ascii=False),
                    "report_summary": json.dumps(
                        {"error_count": len(report.errors)}, ensure_ascii=False
                    ),
                },
            ).scalar_one()
        )
        catalog_ids = _upsert_catalog(
            connection, entries, run_id, deactivate_missing
        )
        _upsert_links(connection, links, catalog_ids, run_id)
        connection.execute(
            text(
                """
                UPDATE oa.legal_regulation_import_run
                SET status = 'success',
                    statistics = CAST(:statistics AS jsonb),
                    report_summary = CAST(:report_summary AS jsonb),
                    completed_at = now()
                WHERE id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "statistics": json.dumps(report.statistics, ensure_ascii=False),
                "report_summary": json.dumps(
                    {
                        "error_count": len(report.errors),
                        "warning_count": len(report.warnings),
                    },
                    ensure_ascii=False,
                ),
            },
        )
    return run_id


def parse_document_ids(value: str | None) -> list[int] | None:
    if not value:
        return None
    candidate = Path(value)
    raw = candidate.read_text("utf-8") if candidate.is_file() else value
    tokens = [token for token in re.split(r"[\s,]+", raw.strip()) if token]
    if any(not re.fullmatch(r"[1-9]\d*", token) for token in tokens):
        raise CatalogValidationError("document-ids必须为正整数清单")
    return sorted({int(token) for token in tokens})


def database_url() -> str:
    configured = os.getenv("ALEMBIC_DATABASE_URL")
    if configured:
        return configured
    user = quote_plus(os.getenv("POSTGRES_USER", "law_rag_user"))
    password = quote_plus(os.getenv("POSTGRES_PASSWORD", "law_rag_password"))
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    database = quote_plus(os.getenv("POSTGRES_DB", "law_rag"))
    return (
        f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"
        "?options=-c%20search_path%3Doa%2Cpublic"
    )


def execute_import(
    *,
    csv_path: Path,
    report_path: Path,
    apply: bool,
    document_ids: Sequence[int] | None,
    deactivate_missing: bool,
    metadata_client: OfficialMetadataClient | None = None,
    engine: Engine | None = None,
) -> ImportReport:
    entries, source_sha256 = read_catalog(csv_path)
    report = ImportReport(
        provider=PROVIDER,
        source_file=str(csv_path),
        source_sha256=source_sha256,
        mode="apply" if apply else "dry-run",
        generated_at=datetime.now(timezone.utc).isoformat(),
        selected_document_ids=list(document_ids) if document_ids else None,
    )
    report.statistics.update(
        {
            "catalog_rows": len(entries),
            "catalog_categories": len({item.category for item in entries}),
            "duplicate_urls": 0,
            "duplicate_external_ids": 0,
        }
    )
    client = metadata_client or OfficialMetadataClient()
    unresolved = enrich_duplicate_metadata(entries, client, report)
    active_engine = engine or create_engine(database_url(), pool_pre_ping=True)
    with active_engine.connect() as connection:
        documents = load_documents(connection, document_ids)
        links = propose_links(entries, documents, unresolved, report)
        if not deactivate_missing:
            missing_count = int(
                connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM oa.legal_regulation_catalog
                        WHERE provider = :provider AND is_current
                          AND NOT (external_id = ANY(:external_ids))
                        """
                    ),
                    {
                        "provider": PROVIDER,
                        "external_ids": [item.external_id for item in entries],
                    },
                ).scalar_one_or_none()
                or 0
            ) if _official_tables_exist(connection) else 0
            report.statistics["existing_catalog_missing_from_csv"] = missing_count
    if apply:
        report.statistics["import_run_id"] = apply_import(
            active_engine,
            entries,
            links,
            report,
            deactivate_missing=deactivate_missing,
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def _official_tables_exist(connection: Connection) -> bool:
    return bool(
        connection.execute(
            text("SELECT to_regclass('oa.legal_regulation_catalog') IS NOT NULL")
        ).scalar()
    )
