"""oa phase 3 4 indexes

Revision ID: 758d3efca92d
Revises: 6b60e2cd5b1c
Create Date: 2026-07-09 11:04:52.326066

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '758d3efca92d'
down_revision: Union[str, Sequence[str], None] = '6b60e2cd5b1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('idx_ops_content_asset_creator_employee_id', 'ops_content_asset', ['creator_employee_id'], unique=False, schema='oa')
    op.create_index('idx_ops_content_asset_file_attachment_id', 'ops_content_asset', ['file_attachment_id'], unique=False, schema='oa')
    op.create_index('idx_ops_content_asset_owner_department_id', 'ops_content_asset', ['owner_department_id'], unique=False, schema='oa')
    op.create_index('idx_ops_ad_creative_asset_id', 'ops_ad_creative', ['asset_id'], unique=False, schema='oa')
    op.create_index('idx_ops_ad_creative_campaign_id', 'ops_ad_creative', ['campaign_id'], unique=False, schema='oa')
    op.create_index('idx_ops_ad_spend_daily_campaign_id', 'ops_ad_spend_daily', ['campaign_id'], unique=False, schema='oa')
    op.create_index('idx_ops_ad_spend_daily_creative_id', 'ops_ad_spend_daily', ['creative_id'], unique=False, schema='oa')
    op.create_index('idx_ops_ad_spend_daily_live_session_id', 'ops_ad_spend_daily', ['live_session_id'], unique=False, schema='oa')
    op.create_index('idx_ops_live_lead_assigned_to_employee_id', 'ops_live_lead', ['assigned_to_employee_id'], unique=False, schema='oa')
    op.create_index('idx_ops_live_lead_lead_id', 'ops_live_lead', ['lead_id'], unique=False, schema='oa')
    op.create_index('idx_ops_live_lead_live_session_id', 'ops_live_lead', ['live_session_id'], unique=False, schema='oa')
    op.create_index('idx_lead_source_touch_campaign_id', 'lead_source_touch', ['campaign_id'], unique=False, schema='oa')
    op.create_index('idx_lead_source_touch_creative_id', 'lead_source_touch', ['creative_id'], unique=False, schema='oa')
    op.create_index('idx_lead_source_touch_lead_id', 'lead_source_touch', ['lead_id'], unique=False, schema='oa')
    op.create_index('idx_crm_lead_client_id', 'crm_lead', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_crm_lead_consultant_employee_id', 'crm_lead', ['consultant_employee_id'], unique=False, schema='oa')
    op.create_index('idx_crm_lead_duplicate_party_id', 'crm_lead', ['duplicate_party_id'], unique=False, schema='oa')
    op.create_index('idx_crm_lead_owner_employee_id', 'crm_lead', ['owner_employee_id'], unique=False, schema='oa')
    op.create_index('idx_crm_lead_primary_party_id', 'crm_lead', ['primary_party_id'], unique=False, schema='oa')
    op.create_index('idx_crm_lead_wechat_added_by', 'crm_lead', ['wechat_added_by'], unique=False, schema='oa')
    op.create_index('idx_lead_party_relation_created_by', 'lead_party_relation', ['created_by'], unique=False, schema='oa')
    op.create_index('idx_lead_party_relation_lead_id', 'lead_party_relation', ['lead_id'], unique=False, schema='oa')
    op.create_index('idx_lead_party_relation_party_id', 'lead_party_relation', ['party_id'], unique=False, schema='oa')
    op.create_index('idx_lead_assignment_log_from_department_id', 'lead_assignment_log', ['from_department_id'], unique=False, schema='oa')
    op.create_index('idx_lead_assignment_log_lead_id', 'lead_assignment_log', ['lead_id'], unique=False, schema='oa')
    op.create_index('idx_lead_assignment_log_to_department_id', 'lead_assignment_log', ['to_department_id'], unique=False, schema='oa')
    op.create_index('idx_lead_assignment_log_to_employee_id', 'lead_assignment_log', ['to_employee_id'], unique=False, schema='oa')
    op.create_index('idx_crm_follow_up_client_id', 'crm_follow_up', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_crm_follow_up_follow_employee_id', 'crm_follow_up', ['follow_employee_id'], unique=False, schema='oa')
    op.create_index('idx_crm_follow_up_lead_id', 'crm_follow_up', ['lead_id'], unique=False, schema='oa')
    op.create_index('idx_crm_consultation_client_id', 'crm_consultation', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_crm_consultation_consultant_employee_id', 'crm_consultation', ['consultant_employee_id'], unique=False, schema='oa')
    op.create_index('idx_crm_consultation_converted_case_id', 'crm_consultation', ['converted_case_id'], unique=False, schema='oa')
    op.create_index('idx_crm_consultation_lead_id', 'crm_consultation', ['lead_id'], unique=False, schema='oa')
    op.create_index('idx_case_conflict_check_case_id', 'case_conflict_check', ['case_id'], unique=False, schema='oa')
    op.create_index('idx_case_conflict_check_check_department_id', 'case_conflict_check', ['check_department_id'], unique=False, schema='oa')
    op.create_index('idx_case_conflict_check_checked_by', 'case_conflict_check', ['checked_by'], unique=False, schema='oa')
    op.create_index('idx_case_conflict_check_client_id', 'case_conflict_check', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_case_conflict_check_lead_id', 'case_conflict_check', ['lead_id'], unique=False, schema='oa')
    op.create_index('idx_case_conflict_check_party_id', 'case_conflict_check', ['party_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_task_assigned_employee_id', 'mkt_call_task', ['assigned_employee_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_task_item_assigned_employee_id', 'mkt_call_task_item', ['assigned_employee_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_task_item_call_task_id', 'mkt_call_task_item', ['call_task_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_task_item_client_id', 'mkt_call_task_item', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_task_item_lead_id', 'mkt_call_task_item', ['lead_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_record_analysis_id', 'mkt_call_record', ['analysis_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_record_call_task_id', 'mkt_call_record', ['call_task_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_record_call_task_item_id', 'mkt_call_record', ['call_task_item_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_record_caller_employee_id', 'mkt_call_record', ['caller_employee_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_record_client_id', 'mkt_call_record', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_record_lead_id', 'mkt_call_record', ['lead_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_record_recording_attachment_id', 'mkt_call_record', ['recording_attachment_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_record_transcription_id', 'mkt_call_record', ['transcription_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_quality_review_call_record_id', 'mkt_call_quality_review', ['call_record_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_quality_review_reviewer_id', 'mkt_call_quality_review', ['reviewer_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_appointment_client_id', 'mkt_appointment', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_appointment_lawyer_employee_id', 'mkt_appointment', ['lawyer_employee_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_appointment_lead_id', 'mkt_appointment', ['lead_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_appointment_reception_employee_id', 'mkt_appointment', ['reception_employee_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_appointment_change_log_appointment_id', 'mkt_appointment_change_log', ['appointment_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_appointment_change_log_lead_id', 'mkt_appointment_change_log', ['lead_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_appointment_change_log_next_appointment_id', 'mkt_appointment_change_log', ['next_appointment_id'], unique=False, schema='oa')
    op.create_index('idx_lead_negotiation_record_analysis_id', 'lead_negotiation_record', ['analysis_id'], unique=False, schema='oa')
    op.create_index('idx_lead_negotiation_record_appointment_id', 'lead_negotiation_record', ['appointment_id'], unique=False, schema='oa')
    op.create_index('idx_lead_negotiation_record_lead_id', 'lead_negotiation_record', ['lead_id'], unique=False, schema='oa')
    op.create_index('idx_lead_negotiation_record_main_negotiator_id', 'lead_negotiation_record', ['main_negotiator_id'], unique=False, schema='oa')
    op.create_index('idx_lead_negotiation_record_transcription_id', 'lead_negotiation_record', ['transcription_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_employee_kpi_target_employee_id', 'mkt_employee_kpi_target', ['employee_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_employee_kpi_result_employee_id', 'mkt_employee_kpi_result', ['employee_id'], unique=False, schema='oa')
    op.create_index('idx_mkt_employee_kpi_result_target_id', 'mkt_employee_kpi_result', ['target_id'], unique=False, schema='oa')
    op.create_index('idx_case_conflict_check_active', 'case_conflict_check', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_crm_follow_up_active', 'crm_follow_up', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_crm_lead_active', 'crm_lead', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_mkt_appointment_active', 'mkt_appointment', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_mkt_call_task_active', 'mkt_call_task', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_ops_ad_campaign_active', 'ops_ad_campaign', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_ops_content_asset_active', 'ops_content_asset', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_ops_live_session_active', 'ops_live_session', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_case_conflict_check_created_at', 'case_conflict_check', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_crm_consultation_created_at', 'crm_consultation', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_crm_follow_up_created_at', 'crm_follow_up', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_crm_lead_created_at', 'crm_lead', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_lead_assignment_log_created_at', 'lead_assignment_log', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_lead_negotiation_record_created_at', 'lead_negotiation_record', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_lead_party_relation_created_at', 'lead_party_relation', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_lead_source_touch_created_at', 'lead_source_touch', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_mkt_appointment_created_at', 'mkt_appointment', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_mkt_appointment_change_log_created_at', 'mkt_appointment_change_log', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_quality_review_created_at', 'mkt_call_quality_review', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_record_created_at', 'mkt_call_record', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_task_created_at', 'mkt_call_task', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_mkt_call_task_item_created_at', 'mkt_call_task_item', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_mkt_employee_kpi_result_created_at', 'mkt_employee_kpi_result', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_mkt_employee_kpi_target_created_at', 'mkt_employee_kpi_target', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_ops_ad_campaign_created_at', 'ops_ad_campaign', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_ops_ad_creative_created_at', 'ops_ad_creative', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_ops_ad_spend_daily_created_at', 'ops_ad_spend_daily', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_ops_content_asset_created_at', 'ops_content_asset', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_ops_live_lead_created_at', 'ops_live_lead', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_ops_live_session_created_at', 'ops_live_session', ['created_at'], unique=False, schema='oa')


def downgrade() -> None:
    """Downgrade schema."""
    pass
