"""add_business_field_closure

Revision ID: c4a8f2e71b9d
Revises: 1e66def48871
Create Date: 2026-07-10 18:00:00.000000

第二步：业务字段闭环。
- case_status_log +4 列：下一步计划、预计完成时间、客户配合、补充材料标记
- case_material +4 列：审核人、审核时间、审核意见、补正要求（reviewed_by 加 FK）
- case_close_review +5 列：客户告知、案件结果、未收款、未开票、归档介质
字典（assigned_role 增加 assistant、新增 case_result / archive_medium）走 Excel + seed_dict_data，不在本迁移灌种。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4a8f2e71b9d'
down_revision: Union[str, Sequence[str], None] = '1e66def48871'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ---- case_status_log +4 ----
    op.add_column('case_status_log',
                  sa.Column('next_step_plan', sa.Text(), nullable=True, comment='下一步工作计划'),
                  schema='oa')
    op.add_column('case_status_log',
                  sa.Column('estimated_complete_at', sa.DateTime(timezone=True), nullable=True, comment='预计完成时间'),
                  schema='oa')
    op.add_column('case_status_log',
                  sa.Column('customer_cooperation', sa.Text(), nullable=True, comment='客户配合情况说明'),
                  schema='oa')
    op.add_column('case_status_log',
                  sa.Column('supplement_material_flag', sa.Boolean(), nullable=True, comment='是否需要客户补充材料'),
                  schema='oa')

    # ---- case_material +4（审核闭环）----
    op.add_column('case_material',
                  sa.Column('reviewed_by', sa.BigInteger(), nullable=True, comment='审核人ID，关联员工表的id字段'),
                  schema='oa')
    op.add_column('case_material',
                  sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True, comment='审核时间'),
                  schema='oa')
    op.add_column('case_material',
                  sa.Column('review_opinion', sa.Text(), nullable=True, comment='审核意见'),
                  schema='oa')
    op.add_column('case_material',
                  sa.Column('supplement_requirement', sa.Text(), nullable=True, comment='补正要求'),
                  schema='oa')
    op.create_foreign_key(
        'fk_case_material_reviewer', 'case_material', 'sys_employee',
        ['reviewed_by'], ['id'],
        source_schema='oa', referent_schema='oa',
    )

    # ---- case_close_review +5（结案快照）----
    op.add_column('case_close_review',
                  sa.Column('customer_notified', sa.Boolean(), nullable=True, comment='是否已告知客户结案'),
                  schema='oa')
    op.add_column('case_close_review',
                  sa.Column('case_result', sa.String(length=50), nullable=True,
                            comment='案件结果，绑定字典「case_result/案件结果」'),
                  schema='oa')
    op.add_column('case_close_review',
                  sa.Column('unpaid_amount', sa.Numeric(16, 2), nullable=True, comment='结案时未收款金额快照'),
                  schema='oa')
    op.add_column('case_close_review',
                  sa.Column('uninvoiced_amount', sa.Numeric(16, 2), nullable=True, comment='结案时未开票金额快照'),
                  schema='oa')
    op.add_column('case_close_review',
                  sa.Column('archive_medium', sa.String(length=50), nullable=True,
                            comment='归档介质，绑定字典「archive_medium/归档介质」'),
                  schema='oa')

    # ---- 索引（外键列 + 高频过滤列）----
    op.create_index('ix_case_material_reviewed_by', 'case_material', ['reviewed_by'], schema='oa')
    op.create_index('ix_case_close_review_case_result', 'case_close_review', ['case_result'], schema='oa')
    op.create_index('ix_case_close_review_archive_medium', 'case_close_review', ['archive_medium'], schema='oa')


def downgrade() -> None:
    """Downgrade schema."""
    # 索引
    op.drop_index('ix_case_close_review_archive_medium', table_name='case_close_review', schema='oa')
    op.drop_index('ix_case_close_review_case_result', table_name='case_close_review', schema='oa')
    op.drop_index('ix_case_material_reviewed_by', table_name='case_material', schema='oa')

    # case_close_review -5
    op.drop_column('case_close_review', 'archive_medium', schema='oa')
    op.drop_column('case_close_review', 'uninvoiced_amount', schema='oa')
    op.drop_column('case_close_review', 'unpaid_amount', schema='oa')
    op.drop_column('case_close_review', 'case_result', schema='oa')
    op.drop_column('case_close_review', 'customer_notified', schema='oa')

    # case_material -4（先 FK 再列）
    op.drop_constraint('fk_case_material_reviewer', 'case_material', schema='oa', type_='foreignkey')
    op.drop_column('case_material', 'supplement_requirement', schema='oa')
    op.drop_column('case_material', 'review_opinion', schema='oa')
    op.drop_column('case_material', 'reviewed_at', schema='oa')
    op.drop_column('case_material', 'reviewed_by', schema='oa')

    # case_status_log -4
    op.drop_column('case_status_log', 'supplement_material_flag', schema='oa')
    op.drop_column('case_status_log', 'customer_cooperation', schema='oa')
    op.drop_column('case_status_log', 'estimated_complete_at', schema='oa')
    op.drop_column('case_status_log', 'next_step_plan', schema='oa')
