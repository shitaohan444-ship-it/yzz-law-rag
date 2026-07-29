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


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value).strip(" ._")
    return cleaned[:80] or "当事人"




def field_applies_to_party_type(field_id: str, values: dict) -> bool:
    match = re.match(r"party\.(plaintiff|defendant)\.(.+)", field_id)
    if not match:
        return True
    role, suffix = match.groups()
    entity_type = values.get(f"party.{role}.entity_type")
    if entity_type not in {"natural_person", "organization"}:
        if values.get(f"party.{role}.organization_name"):
            entity_type = "organization"
        elif values.get(f"party.{role}.name"):
            entity_type = "natural_person"
    organization_fields = {
        "organization_name", "organization_address",
        "organization_registration_address", "organization_phone",
        "unified_social_credit_code", "legal_representative",
    }
    natural_fields = {
        "name", "gender", "birth_date", "ethnicity", "phone", "address",
        "current_address", "id_type", "id_number",
    }
    if entity_type == "organization" and suffix in natural_fields:
        return False
    if entity_type == "natural_person" and suffix in organization_fields:
        return False
    return True


def render(job_id: str, cause: str, values: dict, jobs_root: Path, store) -> tuple[Path, str]:
        config = CAUSES[cause]
        schema_path = Path(__file__).resolve().parents[1] / "template_engine" / "schemas" / config["schema"]
        schema = load_schema(schema_path)
        source = Path(settings.drafting_lite_template_root) / config["template"]
        output_root = jobs_root / job_id / "output"
        output_root.mkdir(parents=True, exist_ok=True)
        normalized = output_root / "normalized.docx"
        compile_template(source, normalized, schema)
        # 从 store 读取当前 warnings，用于检测冲突字段并标记红色
        job_state = store.get(job_id)
        current_warnings = job_state.get("warnings") or [] if job_state else []
        for field in schema.fields:
            if not field_applies_to_party_type(field.field_id, values):
                continue
            should_mark_missing = (
                field.required_policy in {"required", "computed"}
                or field.missing_behavior != "blank"
            )
            if (
                field.field_id not in values
                and field.generation_policy != "user_only"
                and should_mark_missing
            ):
                values[field.field_id] = f"【待补充：{field.label}】"
            # 冲突字段的值后拼接红色警告标记
            elif (
                field.field_id in values
                and field.generation_policy != "user_only"
                and any(f"字段 {field.field_id} " in w for w in current_warnings)
            ):
                existing = values[field.field_id]
                if isinstance(existing, str) and "【冲突值" not in existing:
                    values[field.field_id] = f"{existing}【冲突值，请核对】"

        # 身份证号反推出生日期：第7-14位为YYYYMMDD
        # 必须在"待补充"占位符注入之前执行，否则占位符会误触发跳过条件
        for role in ("plaintiff", "defendant"):
            birth_key = f"party.{role}.birth_date"
            id_key = f"party.{role}.id_number"
            if values.get(birth_key) or not values.get(id_key):
                continue
            id_val = str(values[id_key]).strip()
            if len(id_val) == 18 and id_val[:17].isdigit():
                year = id_val[6:10]
                month = id_val[10:12]
                day = id_val[12:14]
                if 1900 <= int(year) <= 2100 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                    values[birth_key] = f"{year}-{month}-{day}"

        # 住所地与经常居住地互填：一项为空时自动采用另一项的值
        for role in ("plaintiff", "defendant"):
            addr_key = f"party.{role}.address"
            current_key = f"party.{role}.current_address"
            addr_val = values.get(addr_key)
            current_val = values.get(current_key)
            if not addr_val and current_val:
                values[addr_key] = current_val
            elif not current_val and addr_val:
                values[current_key] = addr_val

        plaintiff = str(
            values.get("party.plaintiff.name")
            or values.get("party.plaintiff.organization_name")
            or "当事人"
        )
        filename = f"{config['label']}_{_safe_name(plaintiff)}_起诉状.docx"
        output = output_root / filename
        render_template(normalized, output, schema, values)
        return output, filename
