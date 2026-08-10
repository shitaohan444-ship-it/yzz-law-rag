"""Resolve current display context for knowledge-base documents.

Milvus metadata is a searchable snapshot. Displayed search/chat references are
hydrated from PostgreSQL so a title/category rename or subtree move takes effect
without re-embedding the document.
"""
from dataclasses import dataclass
import logging
import re
from urllib.parse import parse_qs, urlparse

from sqlalchemy import bindparam, text

from app.core.config import settings
from app.core.database import SessionLocal

logger = logging.getLogger("uvicorn.error")
_OFFICIAL_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class OfficialLink:
    provider: str
    source_name: str
    label: str
    url: str
    external_id: str

    def public_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "source_name": self.source_name,
            "label": self.label,
            "url": self.url,
        }


@dataclass(frozen=True)
class CategoryContext:
    doc_title: str
    category_id: int
    name: str
    path: list[str]
    path_ids: list[int]
    effective_sensitive: bool
    official_link: OfficialLink | None = None


_CATEGORY_SQL_BASE = """
    WITH RECURSIVE category_paths AS (
      SELECT c.id, c.parent_id, ARRAY[c.category_name]::text[] AS path,
             ARRAY[c.id]::bigint[] AS path_ids,
             c.sensitive AS effective_sensitive
      FROM oa.kb_category c
      WHERE c.parent_id IS NULL AND c.deleted_at IS NULL
      UNION ALL
      SELECT child.id, child.parent_id, parent.path || child.category_name,
             parent.path_ids || child.id,
             parent.effective_sensitive OR child.sensitive
      FROM oa.kb_category child
      JOIN category_paths parent ON child.parent_id = parent.id
      WHERE child.deleted_at IS NULL
    )
"""

_CATEGORY_SQL = text(
    _CATEGORY_SQL_BASE
    + """
    SELECT d.id AS doc_id, d.doc_title, d.category_id, c.category_name,
           cp.path, cp.path_ids, cp.effective_sensitive
    FROM oa.kb_document d
    JOIN oa.kb_category c ON c.id = d.category_id
    JOIN category_paths cp ON cp.id = d.category_id
    WHERE d.id IN :doc_ids
      AND d.deleted_at IS NULL AND d.status IN ('active', 'staging')
    """
).bindparams(bindparam("doc_ids", expanding=True))

_CATEGORY_WITH_OFFICIAL_LINK_SQL = text(
    _CATEGORY_SQL_BASE
    + """
    SELECT d.id AS doc_id, d.doc_title, d.category_id, c.category_name,
           cp.path, cp.path_ids, cp.effective_sensitive,
           catalog.provider AS official_provider,
           catalog.external_id AS official_external_id,
           catalog.official_url
    FROM oa.kb_document d
    JOIN oa.kb_category c ON c.id = d.category_id
    JOIN category_paths cp ON cp.id = d.category_id
    LEFT JOIN oa.kb_document_regulation_link link
      ON link.document_id = d.id
    LEFT JOIN oa.legal_regulation_catalog catalog
      ON catalog.id = link.catalog_id AND catalog.is_current
    WHERE d.id IN :doc_ids
      AND d.deleted_at IS NULL AND d.status IN ('active', 'staging')
    """
).bindparams(bindparam("doc_ids", expanding=True))


def _safe_official_link(row: dict) -> OfficialLink | None:
    provider = str(row.get("official_provider") or "")
    external_id = str(row.get("official_external_id") or "")
    url = str(row.get("official_url") or "")
    if provider != "npc_flk" or not _OFFICIAL_ID_RE.fullmatch(external_id):
        return None
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "flk.npc.gov.cn"
        or parsed.port is not None
        or parsed.path != "/detail"
        or parsed.fragment
    ):
        return None
    query = parse_qs(parsed.query, keep_blank_values=True)
    if set(query) != {"id"} or query["id"] != [external_id]:
        return None
    return OfficialLink(
        provider=provider,
        source_name="国家法律法规数据库",
        label="官网最新版",
        url=f"https://flk.npc.gov.cn/detail?id={external_id}",
        external_id=external_id,
    )


def resolve_document_categories(doc_ids: list[int]) -> dict[int, CategoryContext]:
    """Return current category data keyed by document id.

    A defensive empty fallback keeps retrieval compatible with isolated unit
    tests and allows old Milvus metadata to remain usable during a transient DB
    read failure. Production requests normally reach PostgreSQL earlier during
    authorization, so this fallback is exceptional and logged.
    """
    normalized = sorted({int(doc_id) for doc_id in doc_ids if int(doc_id) > 0})
    if not normalized:
        return {}
    try:
        with SessionLocal() as db:
            query = (
                _CATEGORY_WITH_OFFICIAL_LINK_SQL
                if settings.rag_official_links_enabled
                else _CATEGORY_SQL
            )
            rows = db.execute(query, {"doc_ids": normalized}).mappings().all()
    except Exception as exc:  # pragma: no cover - defensive runtime fallback
        logger.warning("category_resolution_failed docs=%s error=%s", normalized, type(exc).__name__)
        return {}
    return {
        int(row["doc_id"]): CategoryContext(
            doc_title=str(row["doc_title"]),
            category_id=int(row["category_id"]),
            name=str(row["category_name"]),
            path=[str(item) for item in (row["path"] or [])],
            path_ids=[int(item) for item in (row["path_ids"] or [])],
            effective_sensitive=bool(row["effective_sensitive"]),
            official_link=(
                _safe_official_link(row)
                if settings.rag_official_links_enabled
                else None
            ),
        )
        for row in rows
    }
