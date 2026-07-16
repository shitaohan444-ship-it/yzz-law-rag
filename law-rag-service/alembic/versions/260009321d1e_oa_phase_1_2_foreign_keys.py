"""oa phase 1 2 foreign keys

Revision ID: 260009321d1e
Revises: 2e3faa37c7e7
Create Date: 2026-07-09 10:41:19.932590

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '260009321d1e'
down_revision: Union[str, Sequence[str], None] = '2e3faa37c7e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 第1批：先加 employee.department_id -> department.id，打破循环依赖
    op.create_foreign_key('fk_sys_employee_department', 'sys_employee', 'sys_department', ['department_id'], ['id'], source_schema='oa', referent_schema='oa')

    # 第2批：其他非循环外键
    op.create_foreign_key('fk_sys_dict_item_type', 'sys_dict_item', 'sys_dict_type', ['dict_type_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_dict_item_relation_child', 'sys_dict_item_relation', 'sys_dict_item', ['child_item_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_dict_item_relation_parent', 'sys_dict_item_relation', 'sys_dict_item', ['parent_item_id'], ['id'], source_schema='oa', referent_schema='oa')
    # 注意：sys_dict_field_binding.code_category / region_code 引用 sys_dict_type 的对应字段，
    # 但 sys_dict_type 的唯一约束是 (region_code, code_category)，单独字段不唯一，
    # PostgreSQL 不允许外键引用非唯一列，因此这两个外键在数据库层不加，由应用层保证。
    op.create_foreign_key('fk_sys_department_parent', 'sys_department', 'sys_department', ['parent_department_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_employee_supervisor', 'sys_employee', 'sys_employee', ['supervisor_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_user_employee', 'sys_user', 'sys_employee', ['employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_user_role_employee', 'sys_user_role', 'sys_employee', ['employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_user_role_user', 'sys_user_role', 'sys_user', ['user_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_user_role_role', 'sys_user_role', 'sys_role', ['role_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_storage_repository_created_by', 'sys_storage_repository', 'sys_employee', ['created_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_storage_repository_updated_by', 'sys_storage_repository', 'sys_employee', ['updated_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_nas_folder_rule_department', 'nas_folder_rule', 'sys_department', ['department_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_nas_folder_rule_created_by', 'nas_folder_rule', 'sys_employee', ['created_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_nas_folder_rule_updated_by', 'nas_folder_rule', 'sys_employee', ['updated_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_nas_folder_rule_storage_repository', 'nas_folder_rule', 'sys_storage_repository', ['storage_repository_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_attachment_uploaded_by', 'sys_attachment', 'sys_employee', ['uploaded_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_attachment_storage_repository', 'sys_attachment', 'sys_storage_repository', ['storage_repository_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_attachment_relation_created_by', 'sys_attachment_relation', 'sys_employee', ['created_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_attachment_relation_attachment', 'sys_attachment_relation', 'sys_attachment', ['attachment_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_tag_relation_tag', 'sys_tag_relation', 'sys_tag', ['tag_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_tag_relation_client', 'sys_tag_relation', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_approval_applicant', 'sys_approval_record', 'sys_employee', ['applicant_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_approval_approver', 'sys_approval_record', 'sys_employee', ['approver_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_notification_receiver', 'sys_notification', 'sys_employee', ['receiver_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_operation_log_operator', 'sys_operation_log', 'sys_employee', ['operator_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_data_export_log_approver', 'sys_data_export_log', 'sys_employee', ['approved_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_sys_data_export_log_requester', 'sys_data_export_log', 'sys_employee', ['requester_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_party_main_created_by', 'party_main', 'sys_employee', ['created_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_party_main_updated_by', 'party_main', 'sys_employee', ['updated_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_client_owner', 'crm_client', 'sys_employee', ['owner_employee_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_crm_contact_client', 'crm_contact', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_client_party_relation_created_by', 'client_party_relation', 'sys_employee', ['created_by'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_client_party_relation_party', 'client_party_relation', 'party_main', ['party_id'], ['id'], source_schema='oa', referent_schema='oa')
    op.create_foreign_key('fk_client_party_relation_client', 'client_party_relation', 'crm_client', ['client_id'], ['id'], source_schema='oa', referent_schema='oa')

    # 第3批：循环依赖最后加
    op.create_foreign_key('fk_sys_department_manager', 'sys_department', 'sys_employee', ['manager_employee_id'], ['id'], source_schema='oa', referent_schema='oa')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_sys_department_manager', 'sys_department', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_client_party_relation_client', 'client_party_relation', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_client_party_relation_party', 'client_party_relation', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_client_party_relation_created_by', 'client_party_relation', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_crm_contact_client', 'crm_contact', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_crm_client_owner', 'crm_client', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_party_main_updated_by', 'party_main', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_party_main_created_by', 'party_main', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_data_export_log_requester', 'sys_data_export_log', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_data_export_log_approver', 'sys_data_export_log', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_operation_log_operator', 'sys_operation_log', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_notification_receiver', 'sys_notification', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_approval_approver', 'sys_approval_record', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_approval_applicant', 'sys_approval_record', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_tag_relation_client', 'sys_tag_relation', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_tag_relation_tag', 'sys_tag_relation', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_attachment_relation_attachment', 'sys_attachment_relation', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_attachment_relation_created_by', 'sys_attachment_relation', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_attachment_storage_repository', 'sys_attachment', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_attachment_uploaded_by', 'sys_attachment', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_nas_folder_rule_storage_repository', 'nas_folder_rule', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_nas_folder_rule_updated_by', 'nas_folder_rule', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_nas_folder_rule_created_by', 'nas_folder_rule', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_nas_folder_rule_department', 'nas_folder_rule', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_storage_repository_updated_by', 'sys_storage_repository', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_storage_repository_created_by', 'sys_storage_repository', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_user_role_role', 'sys_user_role', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_user_role_user', 'sys_user_role', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_user_role_employee', 'sys_user_role', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_user_employee', 'sys_user', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_employee_supervisor', 'sys_employee', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_department_parent', 'sys_department', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_dict_item_relation_parent', 'sys_dict_item_relation', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_dict_item_relation_child', 'sys_dict_item_relation', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_dict_item_type', 'sys_dict_item', schema='oa', type_='foreignkey')
    op.drop_constraint('fk_sys_employee_department', 'sys_employee', schema='oa', type_='foreignkey')
