"""oa phase 9 10 indexes

Revision ID: 5995297731e3
Revises: 17c8eba9da04
Create Date: 2026-07-09 11:47:10.649110

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '5995297731e3'
down_revision: Union[str, Sequence[str], None] = '17c8eba9da04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('idx_admin_contract_attachment_id', 'admin_contract', ['attachment_id'], unique=False, schema='oa')
    op.create_index('idx_admin_asset_keeper_employee_id', 'admin_asset', ['keeper_employee_id'], unique=False, schema='oa')
    op.create_index('idx_admin_performance_kpi_confirmed_by', 'admin_performance_kpi', ['confirmed_by'], unique=False, schema='oa')
    op.create_index('idx_admin_performance_kpi_department_id', 'admin_performance_kpi', ['department_id'], unique=False, schema='oa')
    op.create_index('idx_admin_performance_kpi_employee_id', 'admin_performance_kpi', ['employee_id'], unique=False, schema='oa')
    op.create_index('idx_kb_document_attachment_id', 'kb_document', ['attachment_id'], unique=False, schema='oa')
    op.create_index('idx_kb_document_author_employee_id', 'kb_document', ['author_employee_id'], unique=False, schema='oa')
    op.create_index('idx_kb_document_source_department_id', 'kb_document', ['source_department_id'], unique=False, schema='oa')
    op.create_index('idx_ai_chat_log_case_id', 'ai_chat_log', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_ai_transcription_record_attachment_id', 'ai_transcription_record', ['attachment_id'], unique=False, schema='oa')
    op.create_index('idx_ai_transcription_record_created_by', 'ai_transcription_record', ['created_by'], unique=False, schema='oa')
    op.create_index('idx_ai_analysis_record_created_by', 'ai_analysis_record', ['created_by'], unique=False, schema='oa')
    op.create_index('idx_ai_analysis_record_transcription_id', 'ai_analysis_record', ['transcription_id'], unique=False, schema='oa')
    op.create_index('idx_ai_analysis_review_analysis_id', 'ai_analysis_review', ['analysis_id'], unique=False, schema='oa')
    op.create_index('idx_ai_analysis_review_reviewer_id', 'ai_analysis_review', ['reviewer_id'], unique=False, schema='oa')
    op.create_index('idx_admin_asset_active', 'admin_asset', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_admin_performance_kpi_active', 'admin_performance_kpi', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_ai_chat_log_active', 'ai_chat_log', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_kb_document_active', 'kb_document', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_admin_asset_created_at', 'admin_asset', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_admin_contract_created_at', 'admin_contract', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_admin_performance_kpi_created_at', 'admin_performance_kpi', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_ai_analysis_record_created_at', 'ai_analysis_record', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_ai_analysis_review_created_at', 'ai_analysis_review', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_ai_chat_log_created_at', 'ai_chat_log', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_ai_transcription_record_created_at', 'ai_transcription_record', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_kb_document_created_at', 'kb_document', ['created_at'], unique=False, schema='oa')


def downgrade() -> None:
    """Downgrade schema."""
    pass
