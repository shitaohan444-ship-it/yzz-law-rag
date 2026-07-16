"""fix_payment_collection_summary_cartesian

Revision ID: 830234603e96
Revises: b3bda97f0813
Create Date: 2026-07-09 18:47:22.589203

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '830234603e96'
down_revision: Union[str, Sequence[str], None] = 'b3bda97f0813'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """修复 v_payment_collection_summary 因发票、退费直接 JOIN 回款计划而产生的笛卡尔积翻倍问题。"""
    views_dir = Path(__file__).resolve().parent.parent / "views"
    sql_path = views_dir / "v_payment_collection_summary.sql"
    view_sql = sql_path.read_text(encoding="utf-8").strip()
    op.execute(text(f"CREATE OR REPLACE VIEW oa.v_payment_collection_summary AS\n{view_sql}"))


def downgrade() -> None:
    """回滚时重新创建 v1 版本视图（保留原逻辑，仅用于回滚）。"""
    op.execute(text("""
        CREATE OR REPLACE VIEW oa.v_payment_collection_summary AS
        SELECT
            fa.case_id,
            fa.id AS contract_id,
            COALESCE(fa.deal_amount, 0::numeric) AS contract_amount,
            COALESCE(SUM(pp.receivable_amount), 0::numeric) AS receivable_amount,
            COALESCE(SUM(pp.received_amount), 0::numeric) AS paid_amount,
            COALESCE(SUM(pp.receivable_amount - pp.received_amount), 0::numeric) AS unpaid_amount,
            COALESCE(SUM(inv.invoice_amount), 0::numeric) AS invoice_amount,
            COALESCE(SUM(rr.refund_amount), 0::numeric) AS refund_amount,
            COALESCE(MAX(pp.payment_node_status::text), '') AS payment_node_status,
            MAX(pr.received_at::date) AS latest_payment_date
        FROM oa.fin_fee_agreement fa
        LEFT JOIN oa.fin_payment_plan pp
            ON pp.fee_agreement_id = fa.id
            AND pp.deleted_at IS NULL
        LEFT JOIN oa.fin_payment_record pr
            ON pr.payment_plan_id = pp.id
            AND pr.deleted_at IS NULL
        LEFT JOIN oa.fin_invoice inv
            ON inv.case_id = fa.case_id
            AND inv.deleted_at IS NULL
        LEFT JOIN oa.fin_refund_record rr
            ON rr.fee_agreement_id = fa.id
            AND rr.deleted_at IS NULL
        WHERE fa.deleted_at IS NULL
        GROUP BY
            fa.id,
            fa.case_id,
            fa.deal_amount;
    """))
