"""add_v2_16_indexes

Revision ID: 1e66def48871
Revises: 5d5a56832be0
Create Date: 2026-07-10 14:31:59.836450

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e66def48871'
down_revision: Union[str, Sequence[str], None] = '5d5a56832be0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # sys_approval_record biz 关联索引
    op.create_index('ix_sys_approval_record_biz_type', 'sys_approval_record', ['biz_type'], schema='oa')
    op.create_index('ix_sys_approval_record_biz_type_biz_id', 'sys_approval_record', ['biz_type', 'biz_id'], schema='oa')

    # case_intake_review
    op.create_index('ix_case_intake_review_intake_handover_id', 'case_intake_review', ['intake_handover_id'], schema='oa')
    op.create_index('ix_case_intake_review_case_id', 'case_intake_review', ['case_id'], schema='oa')
    op.create_index('ix_case_intake_review_reviewer_id', 'case_intake_review', ['reviewer_id'], schema='oa')
    op.create_index('ix_case_intake_review_review_aspect', 'case_intake_review', ['review_aspect'], schema='oa')
    op.create_index('ix_case_intake_review_created_at', 'case_intake_review', ['created_at'], schema='oa')
    op.create_index('ix_case_intake_review_active', 'case_intake_review', ['status'], schema='oa',
                    postgresql_where=sa.text('deleted_at IS NULL'))

    # case_assignment_history
    op.create_index('ix_case_assignment_history_case_assignment_id', 'case_assignment_history', ['case_assignment_id'], schema='oa')
    op.create_index('ix_case_assignment_history_case_id', 'case_assignment_history', ['case_id'], schema='oa')
    op.create_index('ix_case_assignment_history_new_employee_id', 'case_assignment_history', ['new_employee_id'], schema='oa')
    op.create_index('ix_case_assignment_history_prev_employee_id', 'case_assignment_history', ['previous_employee_id'], schema='oa')
    op.create_index('ix_case_assignment_history_is_current', 'case_assignment_history', ['is_current'], schema='oa')
    op.create_index('ix_case_assignment_history_created_at', 'case_assignment_history', ['created_at'], schema='oa')
    op.create_index('ix_case_assignment_history_active', 'case_assignment_history', ['status'], schema='oa',
                    postgresql_where=sa.text('deleted_at IS NULL'))

    # case_file_handover
    op.create_index('ix_case_file_handover_case_id', 'case_file_handover', ['case_id'], schema='oa')
    op.create_index('ix_case_file_handover_from_employee_id', 'case_file_handover', ['from_employee_id'], schema='oa')
    op.create_index('ix_case_file_handover_to_employee_id', 'case_file_handover', ['to_employee_id'], schema='oa')
    op.create_index('ix_case_file_handover_handover_status', 'case_file_handover', ['handover_status'], schema='oa')
    op.create_index('ix_case_file_handover_created_at', 'case_file_handover', ['created_at'], schema='oa')
    op.create_index('ix_case_file_handover_active', 'case_file_handover', ['status'], schema='oa',
                    postgresql_where=sa.text('deleted_at IS NULL'))

    # case_close_review
    op.create_index('ix_case_close_review_case_id', 'case_close_review', ['case_id'], schema='oa')
    op.create_index('ix_case_close_review_review_type', 'case_close_review', ['review_type'], schema='oa')
    op.create_index('ix_case_close_review_review_status', 'case_close_review', ['review_status'], schema='oa')
    op.create_index('ix_case_close_review_applicant_employee_id', 'case_close_review', ['applicant_employee_id'], schema='oa')
    op.create_index('ix_case_close_review_reviewer_employee_id', 'case_close_review', ['reviewer_employee_id'], schema='oa')
    op.create_index('ix_case_close_review_created_at', 'case_close_review', ['created_at'], schema='oa')
    op.create_index('ix_case_close_review_active', 'case_close_review', ['status'], schema='oa',
                    postgresql_where=sa.text('deleted_at IS NULL'))


def downgrade() -> None:
    """Downgrade schema."""
    # case_close_review
    op.drop_index('ix_case_close_review_active', table_name='case_close_review', schema='oa')
    op.drop_index('ix_case_close_review_created_at', table_name='case_close_review', schema='oa')
    op.drop_index('ix_case_close_review_reviewer_employee_id', table_name='case_close_review', schema='oa')
    op.drop_index('ix_case_close_review_applicant_employee_id', table_name='case_close_review', schema='oa')
    op.drop_index('ix_case_close_review_review_status', table_name='case_close_review', schema='oa')
    op.drop_index('ix_case_close_review_review_type', table_name='case_close_review', schema='oa')
    op.drop_index('ix_case_close_review_case_id', table_name='case_close_review', schema='oa')

    # case_file_handover
    op.drop_index('ix_case_file_handover_active', table_name='case_file_handover', schema='oa')
    op.drop_index('ix_case_file_handover_created_at', table_name='case_file_handover', schema='oa')
    op.drop_index('ix_case_file_handover_handover_status', table_name='case_file_handover', schema='oa')
    op.drop_index('ix_case_file_handover_to_employee_id', table_name='case_file_handover', schema='oa')
    op.drop_index('ix_case_file_handover_from_employee_id', table_name='case_file_handover', schema='oa')
    op.drop_index('ix_case_file_handover_case_id', table_name='case_file_handover', schema='oa')

    # case_assignment_history
    op.drop_index('ix_case_assignment_history_active', table_name='case_assignment_history', schema='oa')
    op.drop_index('ix_case_assignment_history_created_at', table_name='case_assignment_history', schema='oa')
    op.drop_index('ix_case_assignment_history_is_current', table_name='case_assignment_history', schema='oa')
    op.drop_index('ix_case_assignment_history_prev_employee_id', table_name='case_assignment_history', schema='oa')
    op.drop_index('ix_case_assignment_history_new_employee_id', table_name='case_assignment_history', schema='oa')
    op.drop_index('ix_case_assignment_history_case_id', table_name='case_assignment_history', schema='oa')
    op.drop_index('ix_case_assignment_history_case_assignment_id', table_name='case_assignment_history', schema='oa')

    # case_intake_review
    op.drop_index('ix_case_intake_review_active', table_name='case_intake_review', schema='oa')
    op.drop_index('ix_case_intake_review_created_at', table_name='case_intake_review', schema='oa')
    op.drop_index('ix_case_intake_review_review_aspect', table_name='case_intake_review', schema='oa')
    op.drop_index('ix_case_intake_review_reviewer_id', table_name='case_intake_review', schema='oa')
    op.drop_index('ix_case_intake_review_case_id', table_name='case_intake_review', schema='oa')
    op.drop_index('ix_case_intake_review_intake_handover_id', table_name='case_intake_review', schema='oa')

    # sys_approval_record
    op.drop_index('ix_sys_approval_record_biz_type_biz_id', table_name='sys_approval_record', schema='oa')
    op.drop_index('ix_sys_approval_record_biz_type', table_name='sys_approval_record', schema='oa')
