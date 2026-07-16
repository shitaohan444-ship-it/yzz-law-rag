"""add_clerk_rename_agreement_amount_add_payment_node

Revision ID: a2bdf4737b03
Revises: 388d986b4a61
Create Date: 2026-07-10 10:55:15.006881

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
revision: str = 'a2bdf4737b03'
down_revision: Union[str, Sequence[str], None] = '388d986b4a61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 同步列注释（上一轮迁移中模型注释已更新，但数据库端注释未同步）
    op.alter_column('case_assignment', 'case_group',
               existing_type=sa.SMALLINT(),
               comment='案件组别，1=第一组、2=第二组、3=第三组，用于案件分配时按组别管理。',
               existing_comment='案件组别，用于案件分配时按组别管理。',
               existing_nullable=True,
               schema='oa')
    op.alter_column('case_intake_handover', 'archive_review_status',
               existing_type=sa.SMALLINT(),
               comment='卷宗审核状态：1待审核、2审核通过、3退回补充、4审核不通过。',
               existing_comment='卷宗审核状态：pending待审核、approved审核通过、returned退回补充、rejected审核不通过。',
               existing_nullable=True,
               schema='oa')

    # 1. 先删除依赖 fin_fee_agreement.deal_amount 的视图
    op.execute("DROP VIEW IF EXISTS oa.v_case_management_ledger")
    op.execute("DROP VIEW IF EXISTS oa.v_payment_collection_summary")

    # 2. 重命名收费协议金额字段（保留数据）
    op.execute("ALTER TABLE oa.fin_fee_agreement RENAME COLUMN deal_amount TO agreement_amount")

    # 3. 新增庭审书记员字段
    op.add_column('court_hearing', sa.Column('clerk', sa.String(length=100), nullable=True, comment='记录书记员，用于支撑庭审/会议表的业务登记、查询、统计或流程处理。'), schema='oa')

    # 4. 新增回款计划付款节点字段
    op.add_column('fin_payment_plan', sa.Column('payment_node', sa.String(length=80), nullable=True, comment='记录付款节点，用于区分回款计划表中不同业务类别，便于统计、权限控制和后续扩展。该字段应绑定数据字典「payment_node/付款节点」，常见值：sign_first=签约首付款、balance=回款尾款、risk_balance=风险代理尾款、installment=分期款、other=其他，避免各部门手工录入口径不一致。'), schema='oa')

    # 5. 使用新 SQL 重建视图
    _execute_sql_file("v_case_management_ledger_v4.sql", "v_case_management_ledger")
    _execute_sql_file("v_payment_collection_summary_v3.sql", "v_payment_collection_summary")


def downgrade() -> None:
    """Downgrade schema."""
    # 1. 删除依赖 fin_fee_agreement.agreement_amount 的视图
    op.execute("DROP VIEW IF EXISTS oa.v_case_management_ledger")
    op.execute("DROP VIEW IF EXISTS oa.v_payment_collection_summary")

    # 2. 回退新增字段
    op.drop_column('fin_payment_plan', 'payment_node', schema='oa')

    # 3. 重命名收费协议金额字段回原名
    op.execute("ALTER TABLE oa.fin_fee_agreement RENAME COLUMN agreement_amount TO deal_amount")

    # 4. 删除庭审书记员字段
    op.drop_column('court_hearing', 'clerk', schema='oa')

    # 5. 恢复列注释
    op.alter_column('case_intake_handover', 'archive_review_status',
               existing_type=sa.SMALLINT(),
               comment='卷宗审核状态：pending待审核、approved审核通过、returned退回补充、rejected审核不通过。',
               existing_comment='卷宗审核状态：1待审核、2审核通过、3退回补充、4审核不通过。',
               existing_nullable=True,
               schema='oa')
    op.alter_column('case_assignment', 'case_group',
               existing_type=sa.SMALLINT(),
               comment='案件组别，用于案件分配时按组别管理。',
               existing_comment='案件组别，1=第一组、2=第二组、3=第三组，用于案件分配时按组别管理。',
               existing_nullable=True,
               schema='oa')

    # 6. 使用旧 SQL 重建视图
    _execute_sql_file("v_case_management_ledger_v3.sql", "v_case_management_ledger")
    _execute_sql_file("v_payment_collection_summary.sql", "v_payment_collection_summary")
