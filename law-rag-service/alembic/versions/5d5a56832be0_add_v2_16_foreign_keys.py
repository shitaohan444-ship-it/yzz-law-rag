"""add_v2_16_foreign_keys

Revision ID: 5d5a56832be0
Revises: 81b8de685e00
Create Date: 2026-07-10 14:31:06.186579

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d5a56832be0'
down_revision: Union[str, Sequence[str], None] = '81b8de685e00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # case_intake_review
    op.create_foreign_key('fk_case_intake_review_intake_handover', 'case_intake_review', 'case_intake_handover',
                          ['intake_handover_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_intake_review_case', 'case_intake_review', 'case_main',
                          ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_intake_review_reviewer', 'case_intake_review', 'sys_employee',
                          ['reviewer_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_intake_review_previous', 'case_intake_review', 'case_intake_review',
                          ['previous_review_id'], ['id'], source_schema='oa', referent_schema='oa')

    # case_assignment_history
    op.create_foreign_key('fk_case_assignment_history_assignment', 'case_assignment_history', 'case_assignment',
                          ['case_assignment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_assignment_history_case', 'case_assignment_history', 'case_main',
                          ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_assignment_history_prev_emp', 'case_assignment_history', 'sys_employee',
                          ['previous_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_assignment_history_new_emp', 'case_assignment_history', 'sys_employee',
                          ['new_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_assignment_history_request', 'case_assignment_history', 'sys_approval_record',
                          ['adjustment_request_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_assignment_history_archive_reviewer', 'case_assignment_history', 'sys_employee',
                          ['archive_reviewed_by'], ['id'], source_schema='oa', referent_schema='oa')

    # case_file_handover
    op.create_foreign_key('fk_case_file_handover_case', 'case_file_handover', 'case_main',
                          ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_file_handover_from', 'case_file_handover', 'sys_employee',
                          ['from_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_file_handover_to', 'case_file_handover', 'sys_employee',
                          ['to_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_file_handover_archive_reviewer', 'case_file_handover', 'sys_employee',
                          ['archive_reviewed_by'], ['id'], source_schema='oa', referent_schema='oa')

    # case_close_review
    op.create_foreign_key('fk_case_close_review_case', 'case_close_review', 'case_main',
                          ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_close_review_applicant', 'case_close_review', 'sys_employee',
                          ['applicant_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_close_review_reviewer', 'case_close_review', 'sys_employee',
                          ['reviewer_employee_id'], ['id'], source_schema='oa', referent_schema='oa')

    # sys_approval_record 业务对象关联（不做数据库级外键，因为 biz_type/biz_id 是泛型关联）


def downgrade() -> None:
    """Downgrade schema."""
    # case_close_review
    op.drop_constraint('fk_case_close_review_reviewer', 'case_close_review', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_case_close_review_applicant', 'case_close_review', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_case_close_review_case', 'case_close_review', schema='oa', type_='foreignkey')

    # case_file_handover
    op.drop_constraint('fk_case_file_handover_archive_reviewer', 'case_file_handover', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_case_file_handover_to', 'case_file_handover', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_case_file_handover_from', 'case_file_handover', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_case_file_handover_case', 'case_file_handover', schema='oa', type_='foreignkey')

    # case_assignment_history
    op.drop_constraint('fk_case_assignment_history_archive_reviewer', 'case_assignment_history', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_case_assignment_history_request', 'case_assignment_history', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_case_assignment_history_new_emp', 'case_assignment_history', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_case_assignment_history_prev_emp', 'case_assignment_history', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_case_assignment_history_case', 'case_assignment_history', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_case_assignment_history_assignment', 'case_assignment_history', schema='oa', type_='foreignkey')

    # case_intake_review
    op.drop_constraint('fk_case_intake_review_previous', 'case_intake_review', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_case_intake_review_reviewer', 'case_intake_review', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_case_intake_review_case', 'case_intake_review', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_case_intake_review_intake_handover', 'case_intake_review', schema='oa', type_='foreignkey')
