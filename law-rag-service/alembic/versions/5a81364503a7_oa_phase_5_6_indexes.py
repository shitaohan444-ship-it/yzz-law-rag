"""oa phase 5 6 indexes

Revision ID: 5a81364503a7
Revises: 743887d93a8d
Create Date: 2026-07-09 11:18:23.075670

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '5a81364503a7'
down_revision: Union[str, Sequence[str], None] = '743887d93a8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('idx_fin_fee_agreement_case_id', 'fin_fee_agreement', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_fin_fee_agreement_client_id', 'fin_fee_agreement', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_fin_fee_agreement_contract_attachment_id', 'fin_fee_agreement', ['contract_attachment_id'], unique=False, schema='oa')
    op.create_index('idx_fin_fee_agreement_responsible_employee_id', 'fin_fee_agreement', ['responsible_employee_id'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_plan_case_id', 'fin_payment_plan', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_plan_fee_agreement_id', 'fin_payment_plan', ['fee_agreement_id'], unique=False, schema='oa')
    op.create_index('idx_case_intake_handover_ai_analysis_id', 'case_intake_handover', ['ai_analysis_id'], unique=False, schema='oa')
    op.create_index('idx_case_intake_handover_case_id', 'case_intake_handover', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_case_intake_handover_client_id', 'case_intake_handover', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_case_intake_handover_fee_agreement_id', 'case_intake_handover', ['fee_agreement_id'], unique=False, schema='oa')
    op.create_index('idx_case_intake_handover_handover_from_employee_id', 'case_intake_handover', ['handover_from_employee_id'], unique=False, schema='oa')
    op.create_index('idx_case_intake_handover_handover_to_employee_id', 'case_intake_handover', ['handover_to_employee_id'], unique=False, schema='oa')
    op.create_index('idx_case_intake_handover_lead_id', 'case_intake_handover', ['lead_id'], unique=False, schema='oa')
    op.create_index('idx_case_main_case_manager_id', 'case_main', ['case_manager_id'], unique=False, schema='oa')
    op.create_index('idx_case_main_client_id', 'case_main', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_case_main_main_lawyer_id', 'case_main', ['main_lawyer_id'], unique=False, schema='oa')
    op.create_index('idx_case_party_case_id', 'case_party', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_case_party_party_id', 'case_party', ['party_id'], unique=False, schema='oa')
    op.create_index('idx_case_assignment_assigned_by', 'case_assignment', ['assigned_by'], unique=False, schema='oa')
    op.create_index('idx_case_assignment_case_id', 'case_assignment', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_case_assignment_employee_id', 'case_assignment', ['employee_id'], unique=False, schema='oa')
    op.create_index('idx_case_material_attachment_id', 'case_material', ['attachment_id'], unique=False, schema='oa')
    op.create_index('idx_case_material_case_id', 'case_material', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_case_material_received_by', 'case_material', ['received_by'], unique=False, schema='oa')
    op.create_index('idx_case_retrieval_task_assigned_by', 'case_retrieval_task', ['assigned_by'], unique=False, schema='oa')
    op.create_index('idx_case_retrieval_task_assigned_lawyer_id', 'case_retrieval_task', ['assigned_lawyer_id'], unique=False, schema='oa')
    op.create_index('idx_case_retrieval_task_attachment_id', 'case_retrieval_task', ['attachment_id'], unique=False, schema='oa')
    op.create_index('idx_case_retrieval_task_case_id', 'case_retrieval_task', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_case_retrieval_task_created_by', 'case_retrieval_task', ['created_by'], unique=False, schema='oa')
    op.create_index('idx_case_retrieval_task_reviewed_by', 'case_retrieval_task', ['reviewed_by'], unique=False, schema='oa')
    op.create_index('idx_case_retrieval_task_updated_by', 'case_retrieval_task', ['updated_by'], unique=False, schema='oa')
    op.create_index('idx_case_retrieval_task_log_case_id', 'case_retrieval_task_log', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_case_retrieval_task_log_created_by', 'case_retrieval_task_log', ['created_by'], unique=False, schema='oa')
    op.create_index('idx_case_retrieval_task_log_operator_id', 'case_retrieval_task_log', ['operator_id'], unique=False, schema='oa')
    op.create_index('idx_case_retrieval_task_log_retrieval_task_id', 'case_retrieval_task_log', ['retrieval_task_id'], unique=False, schema='oa')
    op.create_index('idx_case_status_log_case_id', 'case_status_log', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_case_status_log_changed_by', 'case_status_log', ['changed_by'], unique=False, schema='oa')
    op.create_index('idx_case_assignment_active', 'case_assignment', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_case_main_active', 'case_main', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_case_material_active', 'case_material', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_case_party_active', 'case_party', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_case_retrieval_task_active', 'case_retrieval_task', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_case_retrieval_task_log_active', 'case_retrieval_task_log', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_case_status_log_active', 'case_status_log', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_fin_fee_agreement_active', 'fin_fee_agreement', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_fin_payment_plan_active', 'fin_payment_plan', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_case_assignment_created_at', 'case_assignment', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_case_intake_handover_created_at', 'case_intake_handover', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_case_main_created_at', 'case_main', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_case_material_created_at', 'case_material', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_case_party_created_at', 'case_party', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_case_retrieval_task_created_at', 'case_retrieval_task', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_case_retrieval_task_log_created_at', 'case_retrieval_task_log', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_case_status_log_created_at', 'case_status_log', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_fin_fee_agreement_created_at', 'fin_fee_agreement', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_plan_created_at', 'fin_payment_plan', ['created_at'], unique=False, schema='oa')


def downgrade() -> None:
    """Downgrade schema."""
    pass
