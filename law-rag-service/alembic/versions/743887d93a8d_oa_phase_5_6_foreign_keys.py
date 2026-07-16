"""oa phase 5 6 foreign keys

Revision ID: 743887d93a8d
Revises: a563fbde197f
Create Date: 2026-07-09 11:17:10.065901

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '743887d93a8d'
down_revision: Union[str, Sequence[str], None] = 'a563fbde197f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_foreign_key('fk_fin_fee_agreement_responsible', 'fin_fee_agreement', 'sys_employee', ['responsible_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_fee_agreement_attachment', 'fin_fee_agreement', 'sys_attachment', ['contract_attachment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_fee_agreement_client', 'fin_fee_agreement', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_fee_agreement_case_id', 'fin_fee_agreement', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_payment_plan_agreement', 'fin_payment_plan', 'fin_fee_agreement', ['fee_agreement_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_payment_plan_case', 'fin_payment_plan', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_handover_from_employee', 'case_intake_handover', 'sys_employee', ['handover_from_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_handover_to_employee', 'case_intake_handover', 'sys_employee', ['handover_to_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_handover_client', 'case_intake_handover', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_handover_lead', 'case_intake_handover', 'crm_lead', ['lead_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_handover_fee_agreement', 'case_intake_handover', 'fin_fee_agreement', ['fee_agreement_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_intake_handover_case_id', 'case_intake_handover', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_main_manager', 'case_main', 'sys_employee', ['case_manager_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_main_lawyer', 'case_main', 'sys_employee', ['main_lawyer_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_main_client', 'case_main', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_party_party_id', 'case_party', 'party_main', ['party_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_party_case', 'case_party', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_assignment_by', 'case_assignment', 'sys_employee', ['assigned_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_assignment_employee', 'case_assignment', 'sys_employee', ['employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_assignment_case', 'case_assignment', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_material_received_by', 'case_material', 'sys_employee', ['received_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_material_attachment', 'case_material', 'sys_attachment', ['attachment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_material_case', 'case_material', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_retrieval_task_assigned_by', 'case_retrieval_task', 'sys_employee', ['assigned_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_retrieval_task_assigned_lawyer', 'case_retrieval_task', 'sys_employee', ['assigned_lawyer_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_retrieval_task_created_by', 'case_retrieval_task', 'sys_employee', ['created_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_retrieval_task_reviewed_by', 'case_retrieval_task', 'sys_employee', ['reviewed_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_retrieval_task_updated_by', 'case_retrieval_task', 'sys_employee', ['updated_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_retrieval_task_attachment', 'case_retrieval_task', 'sys_attachment', ['attachment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_retrieval_task_case', 'case_retrieval_task', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_retrieval_task_log_created_by', 'case_retrieval_task_log', 'sys_employee', ['created_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_retrieval_task_log_operator', 'case_retrieval_task_log', 'sys_employee', ['operator_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_retrieval_task_log_case', 'case_retrieval_task_log', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_retrieval_task_log_task', 'case_retrieval_task_log', 'case_retrieval_task', ['retrieval_task_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_status_log_changed_by', 'case_status_log', 'sys_employee', ['changed_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_status_log_case', 'case_status_log', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')


def downgrade() -> None:
    """Downgrade schema."""
    pass
