"""
读取律所 OA 数据库设计 Excel 的 07/08 sheet，初始化 sys_dict_type 和 sys_dict_item。

Usage:
    .venv\Scripts\python.exe scripts\seed_dict_data.py
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.models.oa_system import SysDictType, SysDictItem

EXCEL_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "律所综合业务数据库v2.16_最终冻结版.xlsx"


def now() -> datetime:
    return datetime.now()


def parse_enum_line(enum_line: str) -> list[dict]:
    """解析 '1=普通；2=敏感；3=机密' 这种格式。"""
    items = []
    if pd.isna(enum_line):
        return items
    for part in str(enum_line).split("；"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            value, label = part.split("=", 1)
            items.append({"value": value.strip(), "label": label.strip()})
    return items


def seed_dict_types_from_07(session: Session) -> None:
    """从 07_字典类型清单 创建/更新 sys_dict_type。"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="07_字典类型清单", header=0)

    # 先清空（幂等）
    session.execute(text("TRUNCATE TABLE oa.sys_dict_item CASCADE"))
    session.execute(text("TRUNCATE TABLE oa.sys_dict_type CASCADE"))

    seen_types: set[str] = set()
    seen_items: set[tuple[str, str]] = set()

    for idx, row in df.iterrows():
        code_category = str(row["字典类别"]).strip()
        category_name = str(row["中文名称"]).strip() if pd.notna(row["中文名称"]) else code_category
        desc = str(row["说明"]).strip() if pd.notna(row["说明"]) else ""

        if code_category not in seen_types:
            seen_types.add(code_category)
            dt = SysDictType(
                region_code="320000",
                indicator_code=code_category,
                code_category=code_category,
                category_name=category_name,
                module_name="oa",
                category_desc=desc,
                sort_order=idx + 1,
                valid_flag=True,
                status="active",
                created_at=now(),
                updated_at=now(),
            )
            session.add(dt)

        # 同时把 07 中的枚举值也作为字典项写入；同一字典类别内去重
        for item_idx, item in enumerate(parse_enum_line(row.get("枚举值/字典值"))):
            key = (code_category, item["value"])
            if key in seen_items:
                continue
            seen_items.add(key)
            session.add(
                SysDictItem(
                    region_code="320000",
                    indicator_code=code_category,
                    code_category=code_category,
                    item_value=item["value"],
                    item_label=item["label"],
                    item_desc="",
                    sort_order=item_idx + 1,
                    valid_flag=True,
                    status="active",
                    created_at=now(),
                    updated_at=now(),
                )
            )

    session.flush()


def seed_dict_items_from_08(session: Session) -> None:
    """从 08_字典值展开表 补充 sys_dict_item。"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="08_字典值展开表", header=0)

    # 按字典编码分组，如果已存在则跳过
    existing = {
        (code_cat, val)
        for code_cat, val in session.query(SysDictItem.code_category, SysDictItem.item_value).all()
    }

    for _, row in df.iterrows():
        code_category = str(row["字典编码"]).strip()
        item_value = str(row["枚举值"]).strip()
        item_label = str(row["枚举显示值"]).strip() if pd.notna(row["枚举显示值"]) else item_value
        sort_order = int(row["排序"]) if pd.notna(row["排序"]) else 0
        valid = str(row.get("是否启用", "")).strip() == "是"

        if (code_category, item_value) in existing:
            continue

        session.add(
            SysDictItem(
                region_code="320000",
                indicator_code=code_category,
                code_category=code_category,
                item_value=item_value,
                item_label=item_label,
                item_desc="",
                sort_order=sort_order,
                valid_flag=valid,
                status="active" if valid else "disabled",
                created_at=now(),
                updated_at=now(),
            )
        )
        existing.add((code_category, item_value))

    session.flush()


def ensure_dict_types_for_08(session: Session) -> None:
    """确保 08 sheet 中所有字典编码在 sys_dict_type 中存在。"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="08_字典值展开表", header=0)
    existing_categories = {c for c, in session.query(SysDictType.code_category).all()}

    for code_category in sorted(df["字典编码"].dropna().unique()):
        code_category = str(code_category).strip()
        if code_category in existing_categories:
            continue
        session.add(
            SysDictType(
                region_code="320000",
                indicator_code=code_category,
                code_category=code_category,
                category_name=code_category,
                module_name="oa",
                category_desc="",
                sort_order=9999,
                valid_flag=True,
                status="active",
                created_at=now(),
                updated_at=now(),
            )
        )
        existing_categories.add(code_category)

    session.flush()


MANUAL_DICT_TYPES: list[dict] = [
    {
        "code_category": "archive_review_status",
        "category_name": "卷宗审核状态",
        "items": [
            {"value": "1", "label": "待审核"},
            {"value": "2", "label": "审核通过"},
            {"value": "3", "label": "退回补充"},
            {"value": "4", "label": "审核不通过"},
        ],
    },
    {
        "code_category": "case_group",
        "category_name": "案件组别",
        "items": [
            {"value": "1", "label": "第一组"},
            {"value": "2", "label": "第二组"},
            {"value": "3", "label": "第三组"},
        ],
    },
    {
        "code_category": "payment_node",
        "category_name": "付款节点",
        "items": [
            {"value": "sign_first", "label": "签约首付款"},
            {"value": "balance", "label": "回款尾款"},
            {"value": "risk_balance", "label": "风险代理尾款"},
            {"value": "installment", "label": "分期款"},
            {"value": "other", "label": "其他"},
        ],
    },
    {
        "code_category": "intake_review_aspect",
        "category_name": "收案审核维度",
        "items": [
            {"value": "1", "label": "委托主体审核"},
            {"value": "2", "label": "合同审核"},
            {"value": "3", "label": "收费审核"},
            {"value": "4", "label": "案件类型审核"},
            {"value": "5", "label": "收案条件审核"},
            {"value": "6", "label": "特殊审批"},
        ],
    },
    {
        "code_category": "review_result",
        "category_name": "审核结果",
        "items": [
            {"value": "1", "label": "通过"},
            {"value": "2", "label": "退回补充"},
            {"value": "3", "label": "不通过"},
        ],
    },
    {
        "code_category": "file_handover_type",
        "category_name": "交接类型",
        "items": [
            {"value": "1", "label": "律师交接"},
            {"value": "2", "label": "部门交接"},
            {"value": "3", "label": "卷宗归档"},
        ],
    },
    {
        "code_category": "file_handover_status",
        "category_name": "交接状态",
        "items": [
            {"value": "1", "label": "待交接"},
            {"value": "2", "label": "交接中"},
            {"value": "3", "label": "已确认"},
            {"value": "4", "label": "退回"},
        ],
    },
    {
        "code_category": "close_review_type",
        "category_name": "结案审核类型",
        "items": [
            {"value": "1", "label": "结案审核"},
            {"value": "2", "label": "归档审核"},
        ],
    },
    {
        "code_category": "close_review_status",
        "category_name": "结案审核状态",
        "items": [
            {"value": "1", "label": "待审核"},
            {"value": "2", "label": "审核通过"},
            {"value": "3", "label": "退回补充"},
            {"value": "4", "label": "审核不通过"},
        ],
    },
]


def ensure_manual_dicts(session: Session) -> None:
    """补充 Excel 中缺失、但业务流程必需的字典类型和字典值（幂等）。"""
    existing_types = {c for c, in session.query(SysDictType.code_category).all()}
    existing_items = {
        (code_cat, val)
        for code_cat, val in session.query(SysDictItem.code_category, SysDictItem.item_value).all()
    }

    for dt in MANUAL_DICT_TYPES:
        code_category = dt["code_category"]
        if code_category not in existing_types:
            session.add(
                SysDictType(
                    region_code="320000",
                    indicator_code=code_category,
                    code_category=code_category,
                    category_name=dt["category_name"],
                    module_name="oa",
                    category_desc="",
                    sort_order=9999,
                    valid_flag=True,
                    status="active",
                    created_at=now(),
                    updated_at=now(),
                )
            )
            existing_types.add(code_category)

        for idx, item in enumerate(dt["items"], start=1):
            if (code_category, item["value"]) in existing_items:
                continue
            session.add(
                SysDictItem(
                    region_code="320000",
                    indicator_code=code_category,
                    code_category=code_category,
                    item_value=item["value"],
                    item_label=item["label"],
                    item_desc="",
                    sort_order=idx,
                    valid_flag=True,
                    status="active",
                    created_at=now(),
                    updated_at=now(),
                )
            )
            existing_items.add((code_category, item["value"]))

    session.flush()


def main() -> int:
    if not EXCEL_PATH.exists():
        print(f"Excel 文件不存在: {EXCEL_PATH}", file=sys.stderr)
        return 1

    engine = create_engine(settings.database_url_with_search_path, future=True)
    with Session(engine) as session:
        seed_dict_types_from_07(session)
        ensure_dict_types_for_08(session)
        seed_dict_items_from_08(session)
        ensure_manual_dicts(session)
        session.commit()

    # 统计
    with engine.connect() as conn:
        type_count = conn.execute(text("SELECT COUNT(*) FROM oa.sys_dict_type")).scalar()
        item_count = conn.execute(text("SELECT COUNT(*) FROM oa.sys_dict_item")).scalar()
        print(f"Seeded {type_count} dict types, {item_count} dict items.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
