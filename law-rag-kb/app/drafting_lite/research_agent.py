from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import httpx
import json
import logging
from pathlib import Path
import re
import time
from typing import Any

from sqlalchemy import bindparam, text

from app.core.config import settings
from app.core.database import SessionLocal
from app.rag.llm import LLMServiceError, get_llm
from app.template_engine import compile_template, load_schema, render_template
from app.drafting_lite.config import (
    AUTHORITY_KEYWORDS,
    CAUSE_FIELDS,
    CAUSES,
    COMMON_FIELDS,
    UNSUPPORTED_DOMAIN_KEYWORDS,
)

logger = logging.getLogger("uvicorn.error")


_LEGAL_CATEGORY_IDS_SQL = text(
    """
    WITH RECURSIVE legal_categories AS (
        SELECT id
          FROM oa.kb_category
         WHERE category_code = 'legal'
           AND deleted_at IS NULL AND status = 'active'
        UNION ALL
        SELECT child.id
          FROM oa.kb_category child
          JOIN legal_categories parent ON child.parent_id = parent.id
         WHERE child.deleted_at IS NULL AND child.status = 'active'
    )
    SELECT id FROM legal_categories
    """
)


def authority_relevant(cause: str, hit: Any) -> bool:
    title = str(getattr(hit, "doc_title", "") or "")
    body = str(getattr(hit, "text", "") or "")
    combined = f"{title}\n{body}"
    matched = [
        keyword
        for keyword in AUTHORITY_KEYWORDS[cause]
        if keyword in combined
    ]
    # 题名直接表明是对应专门法规时，一个命中即可；普通法律条文必须至少
    # 出现两个同领域概念，防止税法、企业法中偶见“贷款/利息”被误引。
    title_specific = any(
        keyword in title
        for keyword in AUTHORITY_KEYWORDS[cause][:2]
    )
    return title_specific or len(matched) >= 2




def retrieve_authorities(cause: str, warnings: list[str]) -> list[dict]:
        try:
            # 检索模型较重，只在研究 Agent 真正执行时加载，避免上传/API 启动阶段占用资源。
            from app.core.authorization import authorized_doc_ids
            from app.core.security import Principal
            from app.rag import retrieve

            with SessionLocal() as db:
                legal_category_ids = [
                    int(value)
                    for value in db.execute(_LEGAL_CATEGORY_IDS_SQL).scalars().all()
                ]
            allowed = authorized_doc_ids(
                Principal(None, None, None, is_service=True, is_admin=True),
                None,
                category_ids=legal_category_ids,
                effective_on=date.today(),
                effectivity_status="active",
                cause_code=CAUSES[cause]["cause_code"],
            )
            cards: list[dict[str, Any]] = []
            seen: set[str] = set()
            for issue in CAUSES[cause]["issues"]:
                for hit in retrieve.search(issue, doc_ids=allowed, top_k=3, min_score=0.3):
                    if hit.chunk_id in seen:
                        continue
                    if not authority_relevant(cause, hit):
                        continue
                    seen.add(hit.chunk_id)
                    cards.append(
                        {
                            "legal_name": hit.doc_title or hit.source,
                            "article_number": hit.article_no,
                            "verified_text": hit.text,
                            "effective_status": "active",
                            "document_id": hit.doc_id,
                            "chunk_id": hit.chunk_id,
                            "content_hash": hashlib.sha256(hit.text.encode("utf-8")).hexdigest(),
                            "retrieval_score": hit.score,
                            "applicable_issue": issue,
                        }
                    )
            if not cards:
                warnings.append("未检索到可核验法条，文书不会补写模型记忆中的条文")
            return cards[:12]
        except Exception:
            warnings.append("法律知识库暂时不可用，已省略未经核验的具体法条")
            return []
