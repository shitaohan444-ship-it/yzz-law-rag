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
    _json_object,
)

logger = logging.getLogger("uvicorn.error")


def draft(
    cause: str,
    fields: dict,
    provenance: dict,
    materials: list[dict],
    cards: list[dict],
    warnings: list[str],
) -> dict:
        verified = {key: value for key, value in fields.items() if provenance.get(key)}
        prompt = """你是要素式起诉状撰写Agent。只能重组已核验字段和法律依据卡片。
不得新增姓名、日期、金额、合同履行、违约事实或法条；缺失字段不要猜测。
返回严格JSON：{"claims":"诉讼请求","facts_and_reasons":"事实与理由"}。
已核验字段：""" + json.dumps(verified, ensure_ascii=False) + "\n依据卡片：" + json.dumps(cards, ensure_ascii=False)
        drafted: dict[str, Any] = {}
        try:
            drafted = _json_object(
                get_llm().generate(prompt, max_tokens=settings.drafting_lite_llm_max_tokens)
            )
        except (LLMServiceError, ValueError, json.JSONDecodeError):
            warnings.append("文书自然语言整理使用了结构化回退结果")
        values = dict(fields)
        claims = str(drafted.get("claims") or fields.get("document.claims") or "").strip()
        facts = str(drafted.get("facts_and_reasons") or fields.get("document.facts_and_reasons") or "").strip()
        if not facts:
            facts = "\n".join(str(value) for key, value in verified.items() if not key.startswith("party."))
        values["document.claims"] = claims or "【待补充：诉讼请求】"
        values["document.facts_and_reasons"] = facts or "【待补充：事实与理由】"
        values["document.legal_basis"] = (
            "\n".join(
                f"《{card['legal_name']}》{card.get('article_number') or ''}：{card['verified_text']}"
                for card in cards[:6]
            )
            or "【未检索到可核验法条】"
        )
        if not values.get("document.evidence_list"):
            values["document.evidence_list"] = [
                {
                    "name": item["file_name"],
                    "page_no": ",".join(
                        str(page["page_no"]) for page in item["page_texts"] if page["page_no"]
                    ) or None,
                    "source": "当事人上传材料",
                    "proof_purpose": "【待补充：证明目的】",
                }
                for item in materials
            ]
        return values
