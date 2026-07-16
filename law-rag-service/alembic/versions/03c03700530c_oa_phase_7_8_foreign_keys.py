"""oa phase 7 8 foreign keys

Revision ID: 03c03700530c
Revises: 4f94159807b0
Create Date: 2026-07-09 11:38:11.809891

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '03c03700530c'
down_revision: Union[str, Sequence[str], None] = '4f94159807b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_foreign_key('fk_legal_work_log_employee', 'legal_work_log', 'sys_employee', ['employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_legal_work_log_case', 'legal_work_log', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_legal_document_draft', 'legal_document', 'sys_employee', ['draft_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_legal_document_review', 'legal_document', 'sys_employee', ['review_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_legal_document_attachment', 'legal_document', 'sys_attachment', ['attachment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_legal_document_case', 'legal_document', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_legal_deadline_responsible', 'legal_deadline', 'sys_employee', ['responsible_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_legal_deadline_case', 'legal_deadline', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_court_hearing_case', 'court_hearing', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_court_hearing_attendee_employee', 'court_hearing_attendee', 'sys_employee', ['employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_court_hearing_attendee_hearing', 'court_hearing_attendee', 'court_hearing', ['hearing_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_evidence_item_case', 'evidence_item', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_evidence_item_material', 'evidence_item', 'case_material', ['material_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_payment_followup_department', 'fin_payment_followup', 'sys_department', ['followup_department_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_payment_followup_employee', 'fin_payment_followup', 'sys_employee', ['followup_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_payment_followup_client', 'fin_payment_followup', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_payment_followup_fee_agreement', 'fin_payment_followup', 'fin_fee_agreement', ['fee_agreement_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_payment_followup_plan', 'fin_payment_followup', 'fin_payment_plan', ['payment_plan_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_payment_followup_case', 'fin_payment_followup', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_payment_record_confirmed_by', 'fin_payment_record', 'sys_employee', ['confirmed_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_payment_record_attachment', 'fin_payment_record', 'sys_attachment', ['receipt_attachment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_payment_record_client', 'fin_payment_record', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_payment_record_plan', 'fin_payment_record', 'fin_payment_plan', ['payment_plan_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_payment_record_case', 'fin_payment_record', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_invoice_attachment', 'fin_invoice', 'sys_attachment', ['invoice_attachment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_invoice_client', 'fin_invoice', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_invoice_case', 'fin_invoice', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_refund_record_created_by', 'fin_refund_record', 'sys_employee', ['created_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_refund_record_approval_record_id', 'fin_refund_record', 'sys_approval_record', ['approval_record_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_refund_record_fee_agreement_id', 'fin_refund_record', 'fin_fee_agreement', ['fee_agreement_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_fin_refund_record_case_id', 'fin_refund_record', 'case_main', ['case_id'], ['id'], source_schema='oa', referent_schema='oa')


def downgrade() -> None:
    """Downgrade schema."""
    pass
