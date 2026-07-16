"""oa phase 9 10 foreign keys

Revision ID: 17c8eba9da04
Revises: 714c66165355
Create Date: 2026-07-09 11:44:44.394589

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17c8eba9da04'
down_revision: Union[str, Sequence[str], None] = '714c66165355'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_foreign_key('fk_admin_contract_attachment', 'admin_contract', 'sys_attachment', ['attachment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_admin_asset_keeper', 'admin_asset', 'sys_employee', ['keeper_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_admin_performance_department', 'admin_performance_kpi', 'sys_department', ['department_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_admin_performance_confirmed_by', 'admin_performance_kpi', 'sys_employee', ['confirmed_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_admin_performance_employee', 'admin_performance_kpi', 'sys_employee', ['employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_kb_document_department', 'kb_document', 'sys_department', ['source_department_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_kb_document_author', 'kb_document', 'sys_employee', ['author_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_kb_document_attachment', 'kb_document', 'sys_attachment', ['attachment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ai_chat_log_case', 'ai_chat_log', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ai_transcription_created_by', 'ai_transcription_record', 'sys_employee', ['created_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ai_transcription_attachment', 'ai_transcription_record', 'sys_attachment', ['attachment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ai_analysis_created_by', 'ai_analysis_record', 'sys_employee', ['created_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ai_analysis_transcription', 'ai_analysis_record', 'ai_transcription_record', ['transcription_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ai_review_reviewer', 'ai_analysis_review', 'sys_employee', ['reviewer_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ai_review_analysis', 'ai_analysis_review', 'ai_analysis_record', ['analysis_id'], ['id'], source_schema='oa', referent_schema='oa')


def downgrade() -> None:
    """Downgrade schema."""
    pass
