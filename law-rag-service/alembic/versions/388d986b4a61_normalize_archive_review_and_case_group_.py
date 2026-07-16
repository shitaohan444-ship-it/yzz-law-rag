"""normalize_archive_review_and_case_group_to_numeric_enum

Revision ID: 388d986b4a61
Revises: 830234603e96
Create Date: 2026-07-10 10:20:16.853894

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


def _execute_sql_file(filename: str, view_name: str) -> None:
    """读取 alembic/views/ 目录下的 SQL 文件并创建视图。"""
    views_dir = Path(__file__).resolve().parent.parent / "views"
    sql_path = views_dir / filename
    sql = sql_path.read_text(encoding="utf-8")
    op.execute(sa.text(f"CREATE VIEW oa.{view_name} AS\n{sql}"))


# revision identifiers, used by Alembic.
revision: str = '388d986b4a61'
down_revision: Union[str, Sequence[str], None] = '830234603e96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Normalize archive_review_status and case_group to numeric enum."""
    # 0. Drop dependent view before altering column types
    op.execute("DROP VIEW IF EXISTS oa.v_case_management_ledger")

    # 1. Migrate existing string values to numeric enum values
    op.execute("""
        UPDATE oa.case_intake_handover
        SET archive_review_status = CASE archive_review_status
            WHEN 'pending' THEN '1'
            WHEN 'approved' THEN '2'
            WHEN 'returned' THEN '3'
            WHEN 'rejected' THEN '4'
            ELSE archive_review_status
        END
        WHERE archive_review_status IS NOT NULL
    """)
    op.execute("""
        UPDATE oa.case_assignment
        SET case_group = CASE case_group
            WHEN 'group_1' THEN '1'
            WHEN 'group_2' THEN '2'
            WHEN 'group_3' THEN '3'
            ELSE case_group
        END
        WHERE case_group IS NOT NULL
    """)

    # 2. Alter column types to SMALLINT
    op.alter_column('case_intake_handover', 'archive_review_status',
                    existing_type=sa.String(length=50),
                    type_=sa.SmallInteger(),
                    existing_nullable=True,
                    schema='oa',
                    postgresql_using='archive_review_status::smallint')
    op.alter_column('case_assignment', 'case_group',
                    existing_type=sa.String(length=50),
                    type_=sa.SmallInteger(),
                    existing_nullable=True,
                    schema='oa',
                    postgresql_using='case_group::smallint')

    # 3. Update dictionary items to numeric values
    op.execute("""
        UPDATE oa.sys_dict_item
        SET item_value = CASE item_label
            WHEN '待审核' THEN '1'
            WHEN '审核通过' THEN '2'
            WHEN '退回补充' THEN '3'
            WHEN '审核不通过' THEN '4'
            ELSE item_value
        END
        WHERE code_category = 'archive_review_status'
    """)
    op.execute("""
        UPDATE oa.sys_dict_item
        SET item_value = CASE item_label
            WHEN '第一组' THEN '1'
            WHEN '第二组' THEN '2'
            WHEN '第三组' THEN '3'
            ELSE item_value
        END
        WHERE code_category = 'case_group'
    """)

    # 4. Update dictionary type descriptions
    op.execute("""
        UPDATE oa.sys_dict_type
        SET category_desc = '1=待审核；2=审核通过；3=退回补充；4=审核不通过'
        WHERE code_category = 'archive_review_status'
    """)
    op.execute("""
        UPDATE oa.sys_dict_type
        SET category_desc = '1=第一组；2=第二组；3=第三组'
        WHERE code_category = 'case_group'
    """)

    # 5. Recreate dependent view with numeric enum columns
    _execute_sql_file("v_case_management_ledger_v3.sql", "v_case_management_ledger")


def downgrade() -> None:
    """Revert numeric enum back to string values."""
    # 0. Drop dependent view before altering column types
    op.execute("DROP VIEW IF EXISTS oa.v_case_management_ledger")

    # 1. Revert column types
    op.alter_column('case_intake_handover', 'archive_review_status',
                    existing_type=sa.SmallInteger(),
                    type_=sa.String(length=50),
                    existing_nullable=True,
                    schema='oa')
    op.alter_column('case_assignment', 'case_group',
                    existing_type=sa.SmallInteger(),
                    type_=sa.String(length=50),
                    existing_nullable=True,
                    schema='oa')

    # 2. Revert data values
    op.execute("""
        UPDATE oa.case_intake_handover
        SET archive_review_status = CASE archive_review_status
            WHEN '1' THEN 'pending'
            WHEN '2' THEN 'approved'
            WHEN '3' THEN 'returned'
            WHEN '4' THEN 'rejected'
            ELSE archive_review_status
        END
        WHERE archive_review_status IS NOT NULL
    """)
    op.execute("""
        UPDATE oa.case_assignment
        SET case_group = CASE case_group
            WHEN '1' THEN 'group_1'
            WHEN '2' THEN 'group_2'
            WHEN '3' THEN 'group_3'
            ELSE case_group
        END
        WHERE case_group IS NOT NULL
    """)

    # 3. Revert dictionary items
    op.execute("""
        UPDATE oa.sys_dict_item
        SET item_value = CASE item_label
            WHEN '待审核' THEN 'pending'
            WHEN '审核通过' THEN 'approved'
            WHEN '退回补充' THEN 'returned'
            WHEN '审核不通过' THEN 'rejected'
            ELSE item_value
        END
        WHERE code_category = 'archive_review_status'
    """)
    op.execute("""
        UPDATE oa.sys_dict_item
        SET item_value = CASE item_label
            WHEN '第一组' THEN 'group_1'
            WHEN '第二组' THEN 'group_2'
            WHEN '第三组' THEN 'group_3'
            ELSE item_value
        END
        WHERE code_category = 'case_group'
    """)

    # 4. Revert dictionary type descriptions
    op.execute("""
        UPDATE oa.sys_dict_type
        SET category_desc = 'pending=待审核；approved=审核通过；returned=退回补充；rejected=审核不通过'
        WHERE code_category = 'archive_review_status'
    """)
    op.execute("""
        UPDATE oa.sys_dict_type
        SET category_desc = 'group_1=第一组；group_2=第二组；group_3=第三组'
        WHERE code_category = 'case_group'
    """)

    # 5. Recreate dependent view with string enum columns
    _execute_sql_file("v_case_management_ledger_v2.sql", "v_case_management_ledger")
