"""oa phase 1 2 indexes

Revision ID: 62955bfb27e4
Revises: 260009321d1e
Create Date: 2026-07-09 10:43:46.744029

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '62955bfb27e4'
down_revision: Union[str, Sequence[str], None] = '260009321d1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('idx_sys_dict_item_dict_type_id', 'sys_dict_item', ['dict_type_id'], unique=False, schema='oa')
    op.create_index('idx_sys_dict_item_relation_child_item_id', 'sys_dict_item_relation', ['child_item_id'], unique=False, schema='oa')
    op.create_index('idx_sys_dict_item_relation_parent_item_id', 'sys_dict_item_relation', ['parent_item_id'], unique=False, schema='oa')
    op.create_index('idx_sys_department_manager_employee_id', 'sys_department', ['manager_employee_id'], unique=False, schema='oa')
    op.create_index('idx_sys_department_parent_department_id', 'sys_department', ['parent_department_id'], unique=False, schema='oa')
    op.create_index('idx_sys_employee_department_id', 'sys_employee', ['department_id'], unique=False, schema='oa')
    op.create_index('idx_sys_employee_supervisor_employee_id', 'sys_employee', ['supervisor_employee_id'], unique=False, schema='oa')
    op.create_index('idx_sys_user_employee_id', 'sys_user', ['employee_id'], unique=False, schema='oa')
    op.create_index('idx_sys_user_role_employee_id', 'sys_user_role', ['employee_id'], unique=False, schema='oa')
    op.create_index('idx_sys_user_role_role_id', 'sys_user_role', ['role_id'], unique=False, schema='oa')
    op.create_index('idx_sys_user_role_user_id', 'sys_user_role', ['user_id'], unique=False, schema='oa')
    op.create_index('idx_sys_storage_repository_created_by', 'sys_storage_repository', ['created_by'], unique=False, schema='oa')
    op.create_index('idx_sys_storage_repository_updated_by', 'sys_storage_repository', ['updated_by'], unique=False, schema='oa')
    op.create_index('idx_nas_folder_rule_created_by', 'nas_folder_rule', ['created_by'], unique=False, schema='oa')
    op.create_index('idx_nas_folder_rule_department_id', 'nas_folder_rule', ['department_id'], unique=False, schema='oa')
    op.create_index('idx_nas_folder_rule_storage_repository_id', 'nas_folder_rule', ['storage_repository_id'], unique=False, schema='oa')
    op.create_index('idx_nas_folder_rule_updated_by', 'nas_folder_rule', ['updated_by'], unique=False, schema='oa')
    op.create_index('idx_sys_attachment_storage_repository_id', 'sys_attachment', ['storage_repository_id'], unique=False, schema='oa')
    op.create_index('idx_sys_attachment_uploaded_by', 'sys_attachment', ['uploaded_by'], unique=False, schema='oa')
    op.create_index('idx_sys_attachment_relation_attachment_id', 'sys_attachment_relation', ['attachment_id'], unique=False, schema='oa')
    op.create_index('idx_sys_attachment_relation_created_by', 'sys_attachment_relation', ['created_by'], unique=False, schema='oa')
    op.create_index('idx_sys_tag_relation_client_id', 'sys_tag_relation', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_sys_tag_relation_tag_id', 'sys_tag_relation', ['tag_id'], unique=False, schema='oa')
    op.create_index('idx_sys_approval_record_applicant_employee_id', 'sys_approval_record', ['applicant_employee_id'], unique=False, schema='oa')
    op.create_index('idx_sys_approval_record_approver_employee_id', 'sys_approval_record', ['approver_employee_id'], unique=False, schema='oa')
    op.create_index('idx_sys_notification_receiver_employee_id', 'sys_notification', ['receiver_employee_id'], unique=False, schema='oa')
    op.create_index('idx_sys_operation_log_operator_id', 'sys_operation_log', ['operator_id'], unique=False, schema='oa')
    op.create_index('idx_sys_data_export_log_approved_by', 'sys_data_export_log', ['approved_by'], unique=False, schema='oa')
    op.create_index('idx_sys_data_export_log_requester_employee_id', 'sys_data_export_log', ['requester_employee_id'], unique=False, schema='oa')
    op.create_index('idx_party_main_created_by', 'party_main', ['created_by'], unique=False, schema='oa')
    op.create_index('idx_party_main_updated_by', 'party_main', ['updated_by'], unique=False, schema='oa')
    op.create_index('idx_crm_client_owner_employee_id', 'crm_client', ['owner_employee_id'], unique=False, schema='oa')
    op.create_index('idx_crm_contact_client_id', 'crm_contact', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_client_party_relation_client_id', 'client_party_relation', ['client_id'], unique=False, schema='oa')
    op.create_index('idx_client_party_relation_created_by', 'client_party_relation', ['created_by'], unique=False, schema='oa')
    op.create_index('idx_client_party_relation_party_id', 'client_party_relation', ['party_id'], unique=False, schema='oa')
    op.create_index('idx_crm_contact_active', 'crm_contact', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_nas_folder_rule_active', 'nas_folder_rule', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_approval_record_active', 'sys_approval_record', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_attachment_active', 'sys_attachment', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_data_export_log_active', 'sys_data_export_log', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_department_active', 'sys_department', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_dict_field_binding_active', 'sys_dict_field_binding', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_dict_item_active', 'sys_dict_item', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_dict_item_relation_active', 'sys_dict_item_relation', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_dict_type_active', 'sys_dict_type', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_employee_active', 'sys_employee', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_notification_active', 'sys_notification', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_role_active', 'sys_role', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_storage_repository_active', 'sys_storage_repository', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_tag_active', 'sys_tag', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_tag_relation_active', 'sys_tag_relation', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_user_active', 'sys_user', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_sys_user_role_active', 'sys_user_role', ['status'], unique=False, schema='oa', postgresql_where=text('deleted_at IS NULL'))
    op.create_index('idx_client_party_relation_created_at', 'client_party_relation', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_crm_client_created_at', 'crm_client', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_crm_contact_created_at', 'crm_contact', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_nas_folder_rule_created_at', 'nas_folder_rule', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_party_main_created_at', 'party_main', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_approval_record_created_at', 'sys_approval_record', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_attachment_created_at', 'sys_attachment', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_attachment_relation_created_at', 'sys_attachment_relation', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_code_sequence_created_at', 'sys_code_sequence', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_data_export_log_created_at', 'sys_data_export_log', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_department_created_at', 'sys_department', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_dict_field_binding_created_at', 'sys_dict_field_binding', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_dict_item_created_at', 'sys_dict_item', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_dict_item_relation_created_at', 'sys_dict_item_relation', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_dict_type_created_at', 'sys_dict_type', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_employee_created_at', 'sys_employee', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_notification_created_at', 'sys_notification', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_operation_log_created_at', 'sys_operation_log', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_role_created_at', 'sys_role', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_storage_repository_created_at', 'sys_storage_repository', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_tag_created_at', 'sys_tag', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_tag_relation_created_at', 'sys_tag_relation', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_user_created_at', 'sys_user', ['created_at'], unique=False, schema='oa')
    op.create_index('idx_sys_user_role_created_at', 'sys_user_role', ['created_at'], unique=False, schema='oa')


def downgrade() -> None:
    """Downgrade schema."""
    pass
