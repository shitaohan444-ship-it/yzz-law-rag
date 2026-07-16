"""oa phase 3 4 foreign keys

Revision ID: 6b60e2cd5b1c
Revises: 8a9579c6a042
Create Date: 2026-07-09 11:00:00.445530

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b60e2cd5b1c'
down_revision: Union[str, Sequence[str], None] = '8a9579c6a042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_foreign_key('fk_ops_content_asset_department', 'ops_content_asset', 'sys_department', ['owner_department_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ops_content_asset_creator', 'ops_content_asset', 'sys_employee', ['creator_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ops_content_asset_attachment', 'ops_content_asset', 'sys_attachment', ['file_attachment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ops_ad_creative_asset_id', 'ops_ad_creative', 'ops_content_asset', ['asset_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ops_ad_creative_campaign_id', 'ops_ad_creative', 'ops_ad_campaign', ['campaign_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ops_ad_spend_daily_campaign_id', 'ops_ad_spend_daily', 'ops_ad_campaign', ['campaign_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ops_ad_spend_daily_creative_id', 'ops_ad_spend_daily', 'ops_ad_creative', ['creative_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ops_ad_spend_daily_live_session_id', 'ops_ad_spend_daily', 'ops_live_session', ['live_session_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ops_live_lead_assigned', 'ops_live_lead', 'sys_employee', ['assigned_to_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ops_live_lead_session', 'ops_live_lead', 'ops_live_session', ['live_session_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_ops_live_lead_lead', 'ops_live_lead', 'crm_lead', ['lead_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_lead_source_touch_campaign_id', 'lead_source_touch', 'ops_ad_campaign', ['campaign_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_lead_source_touch_creative_id', 'lead_source_touch', 'ops_ad_creative', ['creative_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_lead_source_touch_lead_id', 'lead_source_touch', 'crm_lead', ['lead_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_lead_consultant_employee_id', 'crm_lead', 'sys_employee', ['consultant_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_lead_owner', 'crm_lead', 'sys_employee', ['owner_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_lead_wechat_added_by', 'crm_lead', 'sys_employee', ['wechat_added_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_lead_duplicate_party_id', 'crm_lead', 'party_main', ['duplicate_party_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_lead_primary_party_id', 'crm_lead', 'party_main', ['primary_party_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_lead_client', 'crm_lead', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_lead_party_relation_created_by', 'lead_party_relation', 'sys_employee', ['created_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_lead_party_relation_party_id', 'lead_party_relation', 'party_main', ['party_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_lead_party_relation_lead_id', 'lead_party_relation', 'crm_lead', ['lead_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_lead_assignment_log_from_department_id', 'lead_assignment_log', 'sys_department', ['from_department_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_lead_assignment_log_to_department_id', 'lead_assignment_log', 'sys_department', ['to_department_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_lead_assignment_log_to_employee_id', 'lead_assignment_log', 'sys_employee', ['to_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_lead_assignment_log_lead_id', 'lead_assignment_log', 'crm_lead', ['lead_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_follow_up_employee', 'crm_follow_up', 'sys_employee', ['follow_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_follow_up_client', 'crm_follow_up', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_follow_up_lead', 'crm_follow_up', 'crm_lead', ['lead_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_consultation_consultant', 'crm_consultation', 'sys_employee', ['consultant_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_consultation_client', 'crm_consultation', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_consultation_lead', 'crm_consultation', 'crm_lead', ['lead_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_conflict_check_check_department_id', 'case_conflict_check', 'sys_department', ['check_department_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_conflict_check_checked_by', 'case_conflict_check', 'sys_employee', ['checked_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_conflict_check_party_id', 'case_conflict_check', 'party_main', ['party_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_conflict_check_client_id', 'case_conflict_check', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_case_conflict_check_lead_id', 'case_conflict_check', 'crm_lead', ['lead_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_call_task_assigned', 'mkt_call_task', 'sys_employee', ['assigned_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_call_task_item_assigned', 'mkt_call_task_item', 'sys_employee', ['assigned_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_call_task_item_client', 'mkt_call_task_item', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_call_task_item_lead', 'mkt_call_task_item', 'crm_lead', ['lead_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_call_task_item_task', 'mkt_call_task_item', 'mkt_call_task', ['call_task_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_call_record_caller', 'mkt_call_record', 'sys_employee', ['caller_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_call_record_attachment', 'mkt_call_record', 'sys_attachment', ['recording_attachment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_call_record_client', 'mkt_call_record', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_call_record_lead', 'mkt_call_record', 'crm_lead', ['lead_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_call_record_task', 'mkt_call_record', 'mkt_call_task', ['call_task_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_call_record_item', 'mkt_call_record', 'mkt_call_task_item', ['call_task_item_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_call_quality_review_reviewer_id', 'mkt_call_quality_review', 'sys_employee', ['reviewer_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_call_quality_review_call_record_id', 'mkt_call_quality_review', 'mkt_call_record', ['call_record_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_appointment_lawyer', 'mkt_appointment', 'sys_employee', ['lawyer_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_appointment_reception', 'mkt_appointment', 'sys_employee', ['reception_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_appointment_client', 'mkt_appointment', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_appointment_lead', 'mkt_appointment', 'crm_lead', ['lead_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_appointment_change_log_lead_id', 'mkt_appointment_change_log', 'crm_lead', ['lead_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_appointment_change_log_appointment_id', 'mkt_appointment_change_log', 'mkt_appointment', ['appointment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_appointment_change_log_next_appointment_id', 'mkt_appointment_change_log', 'mkt_appointment', ['next_appointment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_lead_negotiation_record_main_negotiator_id', 'lead_negotiation_record', 'sys_employee', ['main_negotiator_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_lead_negotiation_record_lead_id', 'lead_negotiation_record', 'crm_lead', ['lead_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_lead_negotiation_record_appointment_id', 'lead_negotiation_record', 'mkt_appointment', ['appointment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_employee_kpi_target_employee_id', 'mkt_employee_kpi_target', 'sys_employee', ['employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_employee_kpi_result_employee_id', 'mkt_employee_kpi_result', 'sys_employee', ['employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_mkt_employee_kpi_result_target_id', 'mkt_employee_kpi_result', 'mkt_employee_kpi_target', ['target_id'], ['id'], source_schema='oa', referent_schema='oa')


def downgrade() -> None:
    """Downgrade schema."""
    pass
