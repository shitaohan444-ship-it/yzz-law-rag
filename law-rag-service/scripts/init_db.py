"""
律所 OA 数据库初始化统一入口。

执行：
1. Alembic 迁移（创建表、外键、索引）
2. 导入字典种子数据
3. 运行校验

Usage:
    .venv\Scripts\python.exe scripts\init_db.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.models.oa_views import VIEW_NAMES

EXPECTED_TABLES = 80
EXPECTED_VIEWS = 9
EXPECTED_VIEW_NAMES = list(VIEW_NAMES)
EXPECTED_FKS = 200
EXPECTED_INDEXES_MIN = 467
EXPECTED_DICT_TYPES_MIN = 145
EXPECTED_DICT_ITEMS_MIN = 653


def run_alembic_upgrade() -> None:
    print("[init_db] Running alembic upgrade head...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parent.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"Alembic upgrade failed: {result.stderr}")


def run_seed_data() -> None:
    print("[init_db] Seeding dictionary data...")
    result = subprocess.run(
        [sys.executable, "scripts/seed_dict_data.py"],
        cwd=Path(__file__).resolve().parent.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout)


def validate_database() -> None:
    print("[init_db] Validating database...")
    engine = create_engine(settings.database_url_with_search_path, future=True)
    inspector = inspect(engine)

    tables = inspector.get_table_names(schema="oa")
    views = inspector.get_view_names(schema="oa")
    missing_views = set(EXPECTED_VIEW_NAMES) - set(views)

    with engine.connect() as conn:
        fk_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.table_constraints "
                "WHERE table_schema = 'oa' AND constraint_type = 'FOREIGN KEY'"
            )
        ).scalar()
        idx_count = conn.execute(
            text("SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'oa'")
        ).scalar()
        col_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = 'oa'"
            )
        ).scalar()
        dict_type_count = conn.execute(
            text("SELECT COUNT(*) FROM oa.sys_dict_type")
        ).scalar()
        dict_item_count = conn.execute(
            text("SELECT COUNT(*) FROM oa.sys_dict_item")
        ).scalar()

    checks = [
        (len(tables) == EXPECTED_TABLES, f"tables: {len(tables)} (expected {EXPECTED_TABLES})"),
        (len(views) == EXPECTED_VIEWS, f"views: {len(views)} (expected {EXPECTED_VIEWS})"),
        (not missing_views, f"missing views: {missing_views}"),
        (fk_count == EXPECTED_FKS, f"foreign keys: {fk_count} (expected {EXPECTED_FKS})"),
        (idx_count >= EXPECTED_INDEXES_MIN, f"indexes: {idx_count} (expected >= {EXPECTED_INDEXES_MIN})"),
        (dict_type_count >= EXPECTED_DICT_TYPES_MIN, f"dict types: {dict_type_count} (expected >= {EXPECTED_DICT_TYPES_MIN})"),
        (dict_item_count >= EXPECTED_DICT_ITEMS_MIN, f"dict items: {dict_item_count} (expected >= {EXPECTED_DICT_ITEMS_MIN})"),
    ]

    all_passed = True
    for passed, msg in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {msg}")
        if not passed:
            all_passed = False

    print(f"  [INFO] total columns: {col_count}")

    if not all_passed:
        raise RuntimeError("Database validation failed")

    print("[init_db] Validation passed.")


def main() -> int:
    try:
        run_alembic_upgrade()
        run_seed_data()
        validate_database()
        print("[init_db] Database initialization completed successfully.")
        return 0
    except Exception as exc:
        print(f"[init_db] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
