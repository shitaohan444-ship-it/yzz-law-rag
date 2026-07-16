"""
从数据库提取当前 schema 信息，用于修复 Excel 与数据库的不一致。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings

engine = create_engine(settings.database_url_with_search_path, future=True)
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "tmp"
OUTPUT_DIR.mkdir(exist_ok=True)


def fetch_dict_types():
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT id, code, name, description, sort_order, status
            FROM oa.sys_dict_type
            ORDER BY id
        """)).mappings().all()
    return [dict(r) for r in rows]


def fetch_dict_items():
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT id, dict_type_code, item_label, item_value, sort_order, status
            FROM oa.sys_dict_item
            ORDER BY id
        """)).mappings().all()
    return [dict(r) for r in rows]


def fetch_indexes():
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT
                schemaname,
                tablename,
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = 'oa'
            ORDER BY tablename, indexname
        """)).mappings().all()
    return [dict(r) for r in rows]


def fetch_columns():
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT
                c.table_name,
                c.column_name,
                c.data_type,
                c.udt_name,
                c.character_maximum_length,
                c.numeric_precision,
                c.numeric_scale,
                c.is_nullable,
                c.column_default,
                pg_catalog.col_description((c.table_schema || '.' || c.table_name)::regclass::oid, c.ordinal_position) as comment
            FROM information_schema.columns c
            WHERE c.table_schema = 'oa'
              AND c.table_name IN (
                  SELECT table_name FROM information_schema.tables
                  WHERE table_schema = 'oa' AND table_type = 'BASE TABLE'
              )
            ORDER BY c.table_name, c.ordinal_position
        """)).mappings().all()
    return [dict(r) for r in rows]


def main():
    data = {
        "dict_types": fetch_dict_types(),
        "dict_items": fetch_dict_items(),
        "indexes": fetch_indexes(),
        "columns": fetch_columns(),
    }
    out = OUTPUT_DIR / "schema_snapshot.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已导出 schema 快照: {out}")
    print(f"  字典类别: {len(data['dict_types'])}")
    print(f"  字典项: {len(data['dict_items'])}")
    print(f"  索引: {len(data['indexes'])}")
    print(f"  字段: {len(data['columns'])}")


if __name__ == "__main__":
    main()
