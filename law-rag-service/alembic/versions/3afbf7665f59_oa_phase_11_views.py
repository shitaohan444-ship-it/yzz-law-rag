"""oa_phase_11_views

Revision ID: 3afbf7665f59
Revises: 5995297731e3
Create Date: 2026-07-09 12:54:13.392887

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '3afbf7665f59'
down_revision: Union[str, Sequence[str], None] = '5995297731e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PHASE_11_VIEWS = (
    "v_ops_live_effect",
    "v_ops_channel_daily_report",
    "v_lead_conversion_funnel",
    "v_mkt_call_invitation_ledger",
    "v_mkt_visit_negotiation_ledger",
    "v_mkt_employee_performance",
    "v_case_management_ledger",
    "v_case_progress_dashboard",
    "v_payment_collection_summary",
)


def upgrade() -> None:
    """创建第11阶段统计视图。"""
    views_dir = Path(__file__).resolve().parent.parent / "views"
    for view in PHASE_11_VIEWS:
        sql_path = views_dir / f"{view}.sql"
        view_sql = sql_path.read_text(encoding="utf-8").strip()
        op.execute(text(f"CREATE OR REPLACE VIEW oa.{view} AS\n{view_sql}"))


def downgrade() -> None:
    """删除第11阶段统计视图。"""
    for view in reversed(PHASE_11_VIEWS):
        op.execute(text(f"DROP VIEW IF EXISTS oa.{view}"))
