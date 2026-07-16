"""oa phase 7 8 indexes

Revision ID: b7f13ffdc758
Revises: 03c03700530c
Create Date: 2026-07-09 11:39:13.768377

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'b7f13ffdc758'
down_revision: Union[str, Sequence[str], None] = '03c03700530c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('idx_legal_work_log_case_id', 'legal_work_log', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_legal_work_log_employee_id', 'legal_work_log', ['employee_id'], unique=False, schema='oa')
    op.create_index('idx_legal_document_attachment_id', 'legal_document', ['attachment_id'], unique=False, schema='oa')
    op.create_index('idx_legal_document_case_id', 'legal_document', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_legal_document_draft_employee_id', 'legal_document', ['draft_employee_id'], unique=False, schema='oa')
    op.create_index('idx_legal_document_review_employee_id', 'legal_document', ['review_employee_id'], unique=False, schema='oa')
    op.create_index('idx_legal_deadline_case_id', 'legal_deadline', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_legal_deadline_responsible_employee_id', 'legal_deadline', ['responsible_employee_id'], unique=False, schema='oa')
    op.create_index('idx_court_hearing_case_id', 'court_hearing', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_court_hearing_attendee_employee_id', 'court_hearing_attendee', ['employee_id'], unique=False, schema='oa')
    op.create_index('idx_court_hearing_attendee_hearing_id', 'court_hearing_attendee', ['hearing_id'], unique=False, schema='oa')
    op.create_index('idx_evidence_item_case_id', 'evidence_item', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_evidence_item_material_id', 'evidence_item', ['material_id'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_followup_case_id', 'fin_payment_followup', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_followup_client_id', 'fin_payment_followup', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_followup_fee_agreement_id', 'fin_payment_followup', ['fee_agreement_id'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_followup_followup_department_id', 'fin_payment_followup', ['followup_department_id'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_followup_followup_employee_id', 'fin_payment_followup', ['followup_employee_id'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_followup_payment_plan_id', 'fin_payment_followup', ['payment_plan_id'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_record_case_id', 'fin_payment_record', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_record_client_id', 'fin_payment_record', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_record_confirmed_by', 'fin_payment_record', ['confirmed_by'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_record_payment_plan_id', 'fin_payment_record', ['payment_plan_id'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_record_receipt_attachment_id', 'fin_payment_record', ['receipt_attachment_id'], unique=False, schema='oa')
    op.create_index('idx_fin_invoice_case_id', 'fin_invoice', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_fin_invoice_client_id', 'fin_invoice', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_fin_invoice_invoice_attachment_id', 'fin_invoice', ['invoice_attachment_id'], unique=False, schema='oa')
    op.create_index('idx_fin_refund_record_approval_record_id', 'fin_refund_record', ['approval_record_id'], unique=False, schema='oa')
    op.create_index('idx_fin_refund_record_case_id', 'fin_refund_record', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_fin_refund_record_created_by', 'fin_refund_record', ['created_by'], unique=False, schema='oa')
    op.create_index('idx_fin_refund_record_fee_agreement_id', 'fin_refund_record', ['fee_agreement_id'], unique=False, schema='oa')
    op.create_index('idx_court_hearing_active', 'court_hearing', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_court_hearing_attendee_active', 'court_hearing_attendee', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_evidence_item_active', 'evidence_item', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_fin_invoice_active', 'fin_invoice', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_fin_payment_record_active', 'fin_payment_record', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_legal_deadline_active', 'legal_deadline', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_legal_document_active', 'legal_document', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_legal_work_log_active', 'legal_work_log', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_court_hearing_created_at', 'court_hearing', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_court_hearing_attendee_created_at', 'court_hearing_attendee', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_evidence_item_created_at', 'evidence_item', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_fin_invoice_created_at', 'fin_invoice', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_followup_created_at', 'fin_payment_followup', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_fin_payment_record_created_at', 'fin_payment_record', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_fin_refund_record_created_at', 'fin_refund_record', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_legal_deadline_created_at', 'legal_deadline', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_legal_document_created_at', 'legal_document', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_legal_work_log_created_at', 'legal_work_log', ['created_at'], unique=False, schema='oa')


def downgrade() -> None:
    """Downgrade schema."""
    pass
