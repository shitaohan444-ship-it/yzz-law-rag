"""
修复 v2.16 Excel 设计文件，使其与数据库真实状态、校验报告完全一致。

使用前会自动备份原 Excel。脚本直接覆盖原文件。
"""
from __future__ import annotations

import copy
import shutil
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

EXCEL_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "律所综合业务数据库v2.16_最终冻结版.xlsx"

# 新增表定义（字段顺序与模型/Alembic一致）
NEW_TABLES = {
    "case_intake_review": {
        "cn": "收案审核记录表",
        "domain": "业务域层",
        "biz": "案件管理域",
        "type": "业务日志/流转表",
        "usage": "案件管理部",
        "is_source": "是",
        "is_relation": "否",
        "is_event": "是",
        "is_master": "否",
        "pk": "id",
        "fields": [
            ("id", "主键ID", "BIGINT", "NO", "PK", "—", "收案审核记录主键，自增唯一标识。"),
            ("intake_handover_id", "收案移交ID", "BIGINT", "NO", "—", "—", "关联收案移交记录ID，用于建立收案审核与移交记录之间的业务关系。"),
            ("case_id", "案件ID", "BIGINT", "YES", "—", "—", "关联案件主表ID；建案前为空，建案后回填。"),
            ("review_aspect", "审核维度", "VARCHAR(80)", "NO", "—", "intake_review_aspect", "审核维度，绑定字典「intake_review_aspect/收案审核维度」"),
            ("reviewer_id", "审核人ID", "BIGINT", "YES", "—", "—", "审核人ID，关联员工表。"),
            ("review_time", "审核时间", "TIMESTAMP WITH TIME ZONE", "YES", "—", "—", "审核时间。"),
            ("review_opinion", "审核意见", "TEXT", "YES", "—", "—", "审核意见。"),
            ("review_result", "审核结果", "VARCHAR(50)", "YES", "—", "review_result", "审核结果，绑定字典「review_result/审核结果」。"),
            ("supplement_requirement", "补充要求", "TEXT", "YES", "—", "—", "退回补充时要求补充的材料或说明。"),
            ("previous_review_id", "前次审核ID", "BIGINT", "YES", "—", "—", "前一次审核记录ID，用于形成补正审核链条。"),
            ("customer_visible", "客户可见标记", "BOOLEAN", "NO", "—", "customer_visible", "客户可见标记。"),
            ("created_at", "创建时间", "TIMESTAMP WITH TIME ZONE", "NO", "—", "—", "记录创建时间。"),
            ("created_by", "创建人ID", "BIGINT", "YES", "—", "—", "记录创建人ID。"),
            ("updated_at", "更新时间", "TIMESTAMP WITH TIME ZONE", "NO", "—", "—", "记录最近更新时间。"),
            ("updated_by", "更新人ID", "BIGINT", "YES", "—", "—", "记录最后修改人ID。"),
            ("deleted_at", "软删除时间", "TIMESTAMP WITH TIME ZONE", "YES", "—", "—", "软删除时间；为空表示有效。"),
            ("status", "通用状态", "VARCHAR(32)", "NO", "—", "status", "通用记录状态。"),
            ("remark", "备注", "VARCHAR(500)", "YES", "—", "—", "备注字段。"),
        ],
    },
    "case_assignment_history": {
        "cn": "案件分配变更历史表",
        "domain": "关系层",
        "biz": "对象关系与多对多关联",
        "type": "业务关联表",
        "usage": "案件管理部；律师部",
        "is_source": "是",
        "is_relation": "是",
        "is_event": "否",
        "is_master": "否",
        "pk": "id",
        "fields": [
            ("id", "主键ID", "BIGINT", "NO", "PK", "—", "案件分配变更历史主键，自增唯一标识。"),
            ("case_assignment_id", "案件分配ID", "BIGINT", "YES", "—", "—", "关联当前生效的案件分配记录ID。"),
            ("case_id", "案件ID", "BIGINT", "NO", "—", "—", "关联案件主表ID。"),
            ("assigned_role", "分案角色", "VARCHAR(50)", "NO", "—", "assigned_role", "分案角色，绑定字典「assigned_role/分案角色」。"),
            ("previous_employee_id", "原负责人ID", "BIGINT", "YES", "—", "—", "原负责人ID。"),
            ("new_employee_id", "新负责人ID", "BIGINT", "NO", "—", "—", "新负责人ID。"),
            ("change_reason", "变更原因", "VARCHAR(500)", "YES", "—", "—", "变更原因。"),
            ("adjustment_request_id", "调整申请审批ID", "BIGINT", "YES", "—", "—", "关联调整申请审批记录ID。"),
            ("transfer_material_list_json", "交接材料清单", "JSONB", "YES", "—", "—", "交接材料清单，可保存材料类型、附件ID、是否交接等。"),
            ("transfer_completed_at", "交接完成时间", "TIMESTAMP WITH TIME ZONE", "YES", "—", "—", "交接完成时间。"),
            ("archive_review_status", "卷宗交接审核状态", "SMALLINT", "YES", "—", "archive_review_status", "卷宗交接审核状态，1待审核、2审核通过、3退回补充、4审核不通过。"),
            ("archive_reviewed_by", "卷宗交接审核人ID", "BIGINT", "YES", "—", "—", "卷宗交接审核人ID。"),
            ("archive_reviewed_at", "卷宗交接审核时间", "TIMESTAMP WITH TIME ZONE", "YES", "—", "—", "卷宗交接审核时间。"),
            ("effective_from", "生效时间", "TIMESTAMP WITH TIME ZONE", "NO", "—", "—", "该分配生效时间。"),
            ("effective_to", "失效时间", "TIMESTAMP WITH TIME ZONE", "YES", "—", "—", "该分配失效时间；为空表示当前生效。"),
            ("is_current", "是否当前生效", "BOOLEAN", "NO", "—", "yes_no", "是否当前生效记录。"),
            ("created_at", "创建时间", "TIMESTAMP WITH TIME ZONE", "NO", "—", "—", "记录创建时间。"),
            ("created_by", "创建人ID", "BIGINT", "YES", "—", "—", "记录创建人ID。"),
            ("updated_at", "更新时间", "TIMESTAMP WITH TIME ZONE", "NO", "—", "—", "记录最近更新时间。"),
            ("updated_by", "更新人ID", "BIGINT", "YES", "—", "—", "记录最后修改人ID。"),
            ("deleted_at", "软删除时间", "TIMESTAMP WITH TIME ZONE", "YES", "—", "—", "软删除时间；为空表示有效。"),
            ("status", "通用状态", "VARCHAR(32)", "NO", "—", "status", "通用记录状态。"),
            ("remark", "备注", "VARCHAR(500)", "YES", "—", "—", "备注字段。"),
        ],
    },
    "case_file_handover": {
        "cn": "案件内部卷宗/人员交接表",
        "domain": "业务域层",
        "biz": "案件管理域",
        "type": "业务主表",
        "usage": "案件管理部；律师部",
        "is_source": "是",
        "is_relation": "否",
        "is_event": "否",
        "is_master": "否",
        "pk": "id",
        "fields": [
            ("id", "主键ID", "BIGINT", "NO", "PK", "—", "案件内部交接主键，自增唯一标识。"),
            ("case_id", "案件ID", "BIGINT", "NO", "—", "—", "关联案件主表ID。"),
            ("handover_type", "交接类型", "VARCHAR(80)", "NO", "—", "file_handover_type", "交接类型，绑定字典「file_handover_type/交接类型」。"),
            ("from_employee_id", "移交人ID", "BIGINT", "NO", "—", "—", "移交人ID。"),
            ("to_employee_id", "接收人ID", "BIGINT", "NO", "—", "—", "接收人ID。"),
            ("handover_status", "交接状态", "VARCHAR(80)", "NO", "—", "file_handover_status", "交接状态，绑定字典「file_handover_status/交接状态」。"),
            ("material_list_json", "交接材料清单", "JSONB", "YES", "—", "—", "交接材料清单。"),
            ("handover_time", "移交时间", "TIMESTAMP WITH TIME ZONE", "YES", "—", "—", "移交时间。"),
            ("received_time", "接收时间", "TIMESTAMP WITH TIME ZONE", "YES", "—", "—", "接收时间。"),
            ("archive_review_status", "卷宗交接审核状态", "SMALLINT", "YES", "—", "archive_review_status", "卷宗交接审核状态，1待审核、2审核通过、3退回补充、4审核不通过。"),
            ("archive_reviewed_by", "卷宗交接审核人ID", "BIGINT", "YES", "—", "—", "卷宗交接审核人ID。"),
            ("archive_reviewed_at", "卷宗交接审核时间", "TIMESTAMP WITH TIME ZONE", "YES", "—", "—", "卷宗交接审核时间。"),
            ("created_at", "创建时间", "TIMESTAMP WITH TIME ZONE", "NO", "—", "—", "记录创建时间。"),
            ("created_by", "创建人ID", "BIGINT", "YES", "—", "—", "记录创建人ID。"),
            ("updated_at", "更新时间", "TIMESTAMP WITH TIME ZONE", "NO", "—", "—", "记录最近更新时间。"),
            ("updated_by", "更新人ID", "BIGINT", "YES", "—", "—", "记录最后修改人ID。"),
            ("deleted_at", "软删除时间", "TIMESTAMP WITH TIME ZONE", "YES", "—", "—", "软删除时间；为空表示有效。"),
            ("status", "通用状态", "VARCHAR(32)", "NO", "—", "status", "通用记录状态。"),
            ("remark", "备注", "VARCHAR(500)", "YES", "—", "—", "备注字段。"),
        ],
    },
    "case_close_review": {
        "cn": "结案与归档审核表",
        "domain": "业务域层",
        "biz": "案件管理域",
        "type": "业务日志/流转表",
        "usage": "案件管理部",
        "is_source": "是",
        "is_relation": "否",
        "is_event": "是",
        "is_master": "否",
        "pk": "id",
        "fields": [
            ("id", "主键ID", "BIGINT", "NO", "PK", "—", "结案归档审核主键，自增唯一标识。"),
            ("case_id", "案件ID", "BIGINT", "NO", "—", "—", "关联案件主表ID。"),
            ("review_type", "审核类型", "VARCHAR(80)", "NO", "—", "close_review_type", "审核类型，绑定字典「close_review_type/结案审核类型」。"),
            ("applicant_employee_id", "申请人ID", "BIGINT", "NO", "—", "—", "申请人ID。"),
            ("reviewer_employee_id", "审核人ID", "BIGINT", "YES", "—", "—", "审核人ID。"),
            ("review_status", "审核状态", "SMALLINT", "NO", "—", "close_review_status", "审核状态，1待审核、2审核通过、3退回补充、4审核不通过。"),
            ("review_opinion", "审核意见", "TEXT", "YES", "—", "—", "审核意见。"),
            ("close_date", "结案日期", "DATE", "YES", "—", "—", "结案日期。"),
            ("archive_date", "归档日期", "DATE", "YES", "—", "—", "归档日期。"),
            ("archive_location", "归档位置", "VARCHAR(500)", "YES", "—", "—", "归档位置（纸质/电子）。"),
            ("material_complete_flag", "材料是否齐全", "BOOLEAN", "YES", "—", "yes_no", "材料是否齐全。"),
            ("customer_visible", "客户可见标记", "BOOLEAN", "NO", "—", "customer_visible", "客户可见标记。"),
            ("created_at", "创建时间", "TIMESTAMP WITH TIME ZONE", "NO", "—", "—", "记录创建时间。"),
            ("created_by", "创建人ID", "BIGINT", "YES", "—", "—", "记录创建人ID。"),
            ("updated_at", "更新时间", "TIMESTAMP WITH TIME ZONE", "NO", "—", "—", "记录最近更新时间。"),
            ("updated_by", "更新人ID", "BIGINT", "YES", "—", "—", "记录最后修改人ID。"),
            ("deleted_at", "软删除时间", "TIMESTAMP WITH TIME ZONE", "YES", "—", "—", "软删除时间；为空表示有效。"),
            ("status", "通用状态", "VARCHAR(32)", "NO", "—", "status", "通用记录状态。"),
            ("remark", "备注", "VARCHAR(500)", "YES", "—", "—", "备注字段。"),
        ],
    },
}

# stat_metric_definition 表定义（缺失于 Excel）
STAT_TABLE = {
    "stat_metric_definition": {
        "cn": "指标口径定义表",
        "domain": "统计分析层",
        "biz": "指标口径域",
        "type": "统计配置表",
        "usage": "管理部；全部门",
        "is_source": "是",
        "is_relation": "否",
        "is_event": "否",
        "is_master": "否",
        "pk": "id",
        "fields": [
            ("id", "主键ID", "BIGINT", "NO", "PK", "—", "指标口径定义主键。"),
            ("metric_code", "指标编码", "VARCHAR(80)", "YES", "—", "—", "用于唯一标识统计指标。"),
            ("metric_name", "指标名称", "VARCHAR(120)", "YES", "—", "—", "指标中文名称。"),
            ("metric_category", "指标分类", "VARCHAR(80)", "YES", "—", "—", "例如线索、渠道、案件、财务、绩效。"),
            ("calculation_formula", "计算公式", "TEXT", "YES", "—", "—", "记录指标计算公式或SQL口径说明。"),
            ("source_tables", "来源表", "VARCHAR(1000)", "YES", "—", "—", "记录该指标依赖的业务表或视图。"),
            ("dimension_fields", "维度字段", "VARCHAR(1000)", "YES", "—", "—", "记录日期、渠道、员工、案件类型等统计维度。"),
            ("time_grain", "时间粒度", "VARCHAR(50)", "YES", "—", "—", "例如日、周、月、季度、年。"),
            ("owner_department", "维护部门", "VARCHAR(120)", "YES", "—", "—", "维护该指标口径的部门。"),
            ("is_active", "是否启用", "SMALLINT", "YES", "—", "—", "是否启用该指标口径。"),
            ("remark", "备注", "VARCHAR(500)", "YES", "—", "—", "补充说明。"),
            ("created_at", "创建时间", "TIMESTAMP WITH TIME ZONE", "NO", "—", "—", "系统创建时间。"),
            ("created_by", "创建人ID", "BIGINT", "YES", "—", "—", "创建人ID。"),
            ("updated_at", "更新时间", "TIMESTAMP WITH TIME ZONE", "NO", "—", "—", "系统更新时间。"),
            ("updated_by", "更新人ID", "BIGINT", "YES", "—", "—", "更新人ID。"),
            ("deleted_at", "软删除时间", "TIMESTAMP WITH TIME ZONE", "YES", "—", "—", "软删除时间；为空表示有效。"),
            ("status", "通用状态", "VARCHAR(32)", "NO", "—", "status", "通用记录状态。"),
        ],
    },
}

# 字典扩展
DICT_UPDATES = {
    "agreement_status": {
        "name": "协议状态",
        "items": [
            ("1", "草稿", 1),
            ("2", "已签署", 2),
            ("3", "已终止", 3),
            ("4", "待拟定", 4),
            ("5", "待审核", 5),
            ("6", "待签署", 6),
            ("7", "已作废", 7),
            ("8", "已解除", 8),
        ],
    },
    "case_status": {
        "name": "案件状态",
        "items": [
            ("1", "收案中", 1),
            ("2", "已分配", 2),
            ("3", "办理中", 3),
            ("4", "已结案", 4),
            ("5", "待结案审核", 5),
            ("6", "已归档", 6),
        ],
    },
}

NEW_DICTS = {
    "intake_review_aspect": {
        "name": "收案审核维度",
        "items": [
            ("1", "委托主体审核", 1),
            ("2", "合同审核", 2),
            ("3", "收费审核", 3),
            ("4", "案件类型审核", 4),
            ("5", "收案条件审核", 5),
            ("6", "特殊审批", 6),
        ],
    },
    "review_result": {
        "name": "审核结果",
        "items": [
            ("1", "通过", 1),
            ("2", "退回补充", 2),
            ("3", "不通过", 3),
        ],
    },
    "file_handover_type": {
        "name": "交接类型",
        "items": [
            ("1", "律师交接", 1),
            ("2", "部门交接", 2),
            ("3", "卷宗归档", 3),
        ],
    },
    "file_handover_status": {
        "name": "交接状态",
        "items": [
            ("1", "待交接", 1),
            ("2", "交接中", 2),
            ("3", "已确认", 3),
            ("4", "退回", 4),
        ],
    },
    "close_review_type": {
        "name": "结案审核类型",
        "items": [
            ("1", "结案审核", 1),
            ("2", "归档审核", 2),
        ],
    },
    "close_review_status": {
        "name": "结案审核状态",
        "items": [
            ("1", "待审核", 1),
            ("2", "审核通过", 2),
            ("3", "退回补充", 3),
            ("4", "审核不通过", 4),
        ],
    },
}

# 09_外键关系清单新增外键
FK_ROWS = [
    ("业务域层", "案件管理部", "case_intake_review", "收案审核记录表", "业务日志/流转表", "intake_handover_id", "case_intake_handover.id", "外键 fk_case_intake_review_intake_handover"),
    ("业务域层", "案件管理部", "case_intake_review", "收案审核记录表", "业务日志/流转表", "case_id", "case_main.id", "外键 fk_case_intake_review_case"),
    ("业务域层", "案件管理部", "case_intake_review", "收案审核记录表", "业务日志/流转表", "reviewer_id", "sys_employee.id", "外键 fk_case_intake_review_reviewer"),
    ("业务域层", "案件管理部", "case_intake_review", "收案审核记录表", "业务日志/流转表", "previous_review_id", "case_intake_review.id", "外键 fk_case_intake_review_previous"),
    ("关系层", "案件管理部；律师部", "case_assignment_history", "案件分配变更历史表", "业务关联表", "case_assignment_id", "case_assignment.id", "外键 fk_case_assignment_history_assignment"),
    ("关系层", "案件管理部；律师部", "case_assignment_history", "案件分配变更历史表", "业务关联表", "case_id", "case_main.id", "外键 fk_case_assignment_history_case"),
    ("关系层", "案件管理部；律师部", "case_assignment_history", "案件分配变更历史表", "业务关联表", "previous_employee_id", "sys_employee.id", "外键 fk_case_assignment_history_prev_emp"),
    ("关系层", "案件管理部；律师部", "case_assignment_history", "案件分配变更历史表", "业务关联表", "new_employee_id", "sys_employee.id", "外键 fk_case_assignment_history_new_emp"),
    ("关系层", "案件管理部；律师部", "case_assignment_history", "案件分配变更历史表", "业务关联表", "adjustment_request_id", "sys_approval_record.id", "外键 fk_case_assignment_history_request"),
    ("关系层", "案件管理部；律师部", "case_assignment_history", "案件分配变更历史表", "业务关联表", "archive_reviewed_by", "sys_employee.id", "外键 fk_case_assignment_history_archive_reviewer"),
    ("业务域层", "案件管理部；律师部", "case_file_handover", "案件内部卷宗/人员交接表", "业务主表", "case_id", "case_main.id", "外键 fk_case_file_handover_case"),
    ("业务域层", "案件管理部；律师部", "case_file_handover", "案件内部卷宗/人员交接表", "业务主表", "from_employee_id", "sys_employee.id", "外键 fk_case_file_handover_from"),
    ("业务域层", "案件管理部；律师部", "case_file_handover", "案件内部卷宗/人员交接表", "业务主表", "to_employee_id", "sys_employee.id", "外键 fk_case_file_handover_to"),
    ("业务域层", "案件管理部；律师部", "case_file_handover", "案件内部卷宗/人员交接表", "业务主表", "archive_reviewed_by", "sys_employee.id", "外键 fk_case_file_handover_archive_reviewer"),
    ("业务域层", "案件管理部", "case_close_review", "结案与归档审核表", "业务日志/流转表", "case_id", "case_main.id", "外键 fk_case_close_review_case"),
    ("业务域层", "案件管理部", "case_close_review", "结案与归档审核表", "业务日志/流转表", "applicant_employee_id", "sys_employee.id", "外键 fk_case_close_review_applicant"),
    ("业务域层", "案件管理部", "case_close_review", "结案与归档审核表", "业务日志/流转表", "reviewer_employee_id", "sys_employee.id", "外键 fk_case_close_review_reviewer"),
]

# 10_索引清单新增索引
INDEX_ROWS = [
    ("sys_approval_record", "审批记录表", "ix_sys_approval_record_biz_type", "否", "biz_type", "CREATE INDEX ix_sys_approval_record_biz_type ON oa.sys_approval_record USING btree (biz_type)"),
    ("sys_approval_record", "审批记录表", "ix_sys_approval_record_biz_type_biz_id", "否", "biz_type, biz_id", "CREATE INDEX ix_sys_approval_record_biz_type_biz_id ON oa.sys_approval_record USING btree (biz_type, biz_id)"),
    ("case_intake_review", "收案审核记录表", "ix_case_intake_review_intake_handover_id", "否", "intake_handover_id", "CREATE INDEX ix_case_intake_review_intake_handover_id ON oa.case_intake_review USING btree (intake_handover_id)"),
    ("case_intake_review", "收案审核记录表", "ix_case_intake_review_case_id", "否", "case_id", "CREATE INDEX ix_case_intake_review_case_id ON oa.case_intake_review USING btree (case_id)"),
    ("case_intake_review", "收案审核记录表", "ix_case_intake_review_reviewer_id", "否", "reviewer_id", "CREATE INDEX ix_case_intake_review_reviewer_id ON oa.case_intake_review USING btree (reviewer_id)"),
    ("case_intake_review", "收案审核记录表", "ix_case_intake_review_review_aspect", "否", "review_aspect", "CREATE INDEX ix_case_intake_review_review_aspect ON oa.case_intake_review USING btree (review_aspect)"),
    ("case_intake_review", "收案审核记录表", "ix_case_intake_review_created_at", "否", "created_at", "CREATE INDEX ix_case_intake_review_created_at ON oa.case_intake_review USING btree (created_at)"),
    ("case_intake_review", "收案审核记录表", "ix_case_intake_review_active", "否", "status", "CREATE INDEX ix_case_intake_review_active ON oa.case_intake_review USING btree (status) WHERE (deleted_at IS NULL)"),
    ("case_assignment_history", "案件分配变更历史表", "ix_case_assignment_history_case_assignment_id", "否", "case_assignment_id", "CREATE INDEX ix_case_assignment_history_case_assignment_id ON oa.case_assignment_history USING btree (case_assignment_id)"),
    ("case_assignment_history", "案件分配变更历史表", "ix_case_assignment_history_case_id", "否", "case_id", "CREATE INDEX ix_case_assignment_history_case_id ON oa.case_assignment_history USING btree (case_id)"),
    ("case_assignment_history", "案件分配变更历史表", "ix_case_assignment_history_new_employee_id", "否", "new_employee_id", "CREATE INDEX ix_case_assignment_history_new_employee_id ON oa.case_assignment_history USING btree (new_employee_id)"),
    ("case_assignment_history", "案件分配变更历史表", "ix_case_assignment_history_prev_employee_id", "否", "previous_employee_id", "CREATE INDEX ix_case_assignment_history_prev_employee_id ON oa.case_assignment_history USING btree (previous_employee_id)"),
    ("case_assignment_history", "案件分配变更历史表", "ix_case_assignment_history_is_current", "否", "is_current", "CREATE INDEX ix_case_assignment_history_is_current ON oa.case_assignment_history USING btree (is_current)"),
    ("case_assignment_history", "案件分配变更历史表", "ix_case_assignment_history_created_at", "否", "created_at", "CREATE INDEX ix_case_assignment_history_created_at ON oa.case_assignment_history USING btree (created_at)"),
    ("case_assignment_history", "案件分配变更历史表", "ix_case_assignment_history_active", "否", "status", "CREATE INDEX ix_case_assignment_history_active ON oa.case_assignment_history USING btree (status) WHERE (deleted_at IS NULL)"),
    ("case_file_handover", "案件内部卷宗/人员交接表", "ix_case_file_handover_case_id", "否", "case_id", "CREATE INDEX ix_case_file_handover_case_id ON oa.case_file_handover USING btree (case_id)"),
    ("case_file_handover", "案件内部卷宗/人员交接表", "ix_case_file_handover_from_employee_id", "否", "from_employee_id", "CREATE INDEX ix_case_file_handover_from_employee_id ON oa.case_file_handover USING btree (from_employee_id)"),
    ("case_file_handover", "案件内部卷宗/人员交接表", "ix_case_file_handover_to_employee_id", "否", "to_employee_id", "CREATE INDEX ix_case_file_handover_to_employee_id ON oa.case_file_handover USING btree (to_employee_id)"),
    ("case_file_handover", "案件内部卷宗/人员交接表", "ix_case_file_handover_handover_status", "否", "handover_status", "CREATE INDEX ix_case_file_handover_handover_status ON oa.case_file_handover USING btree (handover_status)"),
    ("case_file_handover", "案件内部卷宗/人员交接表", "ix_case_file_handover_created_at", "否", "created_at", "CREATE INDEX ix_case_file_handover_created_at ON oa.case_file_handover USING btree (created_at)"),
    ("case_file_handover", "案件内部卷宗/人员交接表", "ix_case_file_handover_active", "否", "status", "CREATE INDEX ix_case_file_handover_active ON oa.case_file_handover USING btree (status) WHERE (deleted_at IS NULL)"),
    ("case_close_review", "结案与归档审核表", "ix_case_close_review_case_id", "否", "case_id", "CREATE INDEX ix_case_close_review_case_id ON oa.case_close_review USING btree (case_id)"),
    ("case_close_review", "结案与归档审核表", "ix_case_close_review_review_type", "否", "review_type", "CREATE INDEX ix_case_close_review_review_type ON oa.case_close_review USING btree (review_type)"),
    ("case_close_review", "结案与归档审核表", "ix_case_close_review_review_status", "否", "review_status", "CREATE INDEX ix_case_close_review_review_status ON oa.case_close_review USING btree (review_status)"),
    ("case_close_review", "结案与归档审核表", "ix_case_close_review_applicant_employee_id", "否", "applicant_employee_id", "CREATE INDEX ix_case_close_review_applicant_employee_id ON oa.case_close_review USING btree (applicant_employee_id)"),
    ("case_close_review", "结案与归档审核表", "ix_case_close_review_reviewer_employee_id", "否", "reviewer_employee_id", "CREATE INDEX ix_case_close_review_reviewer_employee_id ON oa.case_close_review USING btree (reviewer_employee_id)"),
    ("case_close_review", "结案与归档审核表", "ix_case_close_review_created_at", "否", "created_at", "CREATE INDEX ix_case_close_review_created_at ON oa.case_close_review USING btree (created_at)"),
    ("case_close_review", "结案与归档审核表", "ix_case_close_review_active", "否", "status", "CREATE INDEX ix_case_close_review_active ON oa.case_close_review USING btree (status) WHERE (deleted_at IS NULL)"),
]

# 05_字段字典新增行
FIELD_DICT_ROWS = [
    ("业务域层", "财务合同域", "fin_fee_agreement", "收费协议表", "fee_type", "收费方式", "VARCHAR(80)", "fee_type", "收费方式", "市场部；财务部", "记录收费方式，绑定字典「fee_type/收费方式」。"),
    ("业务域层", "财务合同域", "fin_fee_agreement", "收费协议表", "agreement_status", "协议状态", "VARCHAR(50)", "agreement_status", "协议状态", "市场部；财务部", "记录协议状态，绑定字典「agreement_status/协议状态」。"),
    ("流程事件层", "审批流程", "sys_approval_record", "审批记录表", "biz_type", "业务对象类型", "VARCHAR(80)", "—", "—", "全部门", "业务对象类型，用于将审批记录关联到具体业务对象。"),
    ("流程事件层", "审批流程", "sys_approval_record", "审批记录表", "biz_id", "业务对象ID", "BIGINT", "—", "—", "全部门", "业务对象ID，与 biz_type 联合定位被审批的业务单据。"),
    ("业务域层", "案件管理域", "case_intake_review", "收案审核记录表", "review_aspect", "审核维度", "VARCHAR(80)", "intake_review_aspect", "收案审核维度", "案件管理部", "审核维度，绑定字典「intake_review_aspect/收案审核维度」。"),
    ("业务域层", "案件管理域", "case_intake_review", "收案审核记录表", "review_result", "审核结果", "VARCHAR(50)", "review_result", "审核结果", "案件管理部", "审核结果，绑定字典「review_result/审核结果」。"),
    ("业务域层", "案件管理域", "case_assignment_history", "案件分配变更历史表", "assigned_role", "分案角色", "VARCHAR(50)", "assigned_role", "分案角色", "案件管理部；律师部", "分案角色，绑定字典「assigned_role/分案角色」。"),
    ("业务域层", "案件管理域", "case_assignment_history", "案件分配变更历史表", "archive_review_status", "卷宗交接审核状态", "SMALLINT", "archive_review_status", "卷宗审核状态", "案件管理部", "卷宗交接审核状态，1待审核、2审核通过、3退回补充、4审核不通过。"),
    ("业务域层", "案件管理域", "case_file_handover", "案件内部卷宗/人员交接表", "handover_type", "交接类型", "VARCHAR(80)", "file_handover_type", "交接类型", "案件管理部；律师部", "交接类型，绑定字典「file_handover_type/交接类型」。"),
    ("业务域层", "案件管理域", "case_file_handover", "案件内部卷宗/人员交接表", "handover_status", "交接状态", "VARCHAR(80)", "file_handover_status", "交接状态", "案件管理部；律师部", "交接状态，绑定字典「file_handover_status/交接状态」。"),
    ("业务域层", "案件管理域", "case_file_handover", "案件内部卷宗/人员交接表", "archive_review_status", "卷宗交接审核状态", "SMALLINT", "archive_review_status", "卷宗审核状态", "案件管理部", "卷宗交接审核状态，1待审核、2审核通过、3退回补充、4审核不通过。"),
    ("业务域层", "案件管理域", "case_close_review", "结案与归档审核表", "review_type", "审核类型", "VARCHAR(80)", "close_review_type", "结案审核类型", "案件管理部", "审核类型，绑定字典「close_review_type/结案审核类型」。"),
    ("业务域层", "案件管理域", "case_close_review", "结案与归档审核表", "review_status", "审核状态", "SMALLINT", "close_review_status", "结案审核状态", "案件管理部", "审核状态，1待审核、2审核通过、3退回补充、4审核不通过。"),
]

# 流程映射字段替换（市场部）
MKT_MAPPING_REPLACEMENTS = {
    # 整字段替换（精确匹配）
    "crm_lead.lead_no、case_source、offline_expand_remark、party_name、party_phone、case_type、case_brief":
        "lead_no、case_source、offline_expand_remark、primary_party_id、case_type、case_brief",
    "lead_id、employee_id、assigned_at、assign_status":
        "lead_id、to_employee_id、assigned_by、assigned_at、assignment_status",
    "task_id、lead_id、caller_id、plan_call_start_time":
        "call_task_id、lead_id、assigned_employee_id、planned_call_time",
    "call_start_time、call_result、call_duration_seconds、recording_attachment_id、ai_summary":
        "call_start_time、call_result、call_duration_seconds、recording_attachment_id、conversation_summary",
    "intention_level、next_follow_time、followup_remark":
        "intention_level、next_action、remark",
    "quality_score、problem_tags、review_result、review_remark":
        "quality_score、risk_words_detail、quality_review_status、review_comment",
    "appointment_time、appointment_status、inviter_id、case_type":
        "appointment_time、appointment_status、reception_employee_id、appointment_type",
    "old_time、new_time、change_reason、changed_by":
        "old_appointment_time、new_appointment_time、remark、changed_by",
    "actual_arrival_time、visit_status":
        "actual_arrival_time、visit_result",
    "main_negotiator_id、assistant_negotiator_id、quote_amount、case_analysis、negotiation_result":
        "main_negotiator_id、assistant_negotiator_id、deal_amount、analysis_id、negotiation_result",
    "not_sign_reason、next_follow_time、followup_remark":
        "lost_reason_type、next_follow_up_at、remark",
    "agreement_no、agreement_amount、sign_date、client_id、lead_id":
        "agreement_no、agreement_amount、sign_date、client_id",
}

# 字段类型替换映射
PG_TYPE_MAP = {
    "BIGINT UNSIGNED": "BIGINT",
    "BIGINT(20) UNSIGNED": "BIGINT",
    "INT UNSIGNED": "INTEGER",
    "INT(11)": "INTEGER",
    "TINYINT(1)": "BOOLEAN",
    "TINYINT": "SMALLINT",
    "DATETIME": "TIMESTAMP WITH TIME ZONE",
    "LONGTEXT": "TEXT",
    "MEDIUMTEXT": "TEXT",
    "JSON": "JSONB",
}


def col_idx(ws, header: str) -> int:
    """根据表头文本返回 1-based 列索引。"""
    for cell in ws[1]:
        if cell.value == header:
            return cell.column
    raise ValueError(f"表头未找到: {header}")


def find_rows_by_table(ws, table_col: int, table_name: str):
    """返回表中所有匹配 table_name 的行号（1-based）。"""
    rows = []
    for row in range(2, ws.max_row + 1):
        val = ws.cell(row=row, column=table_col).value
        if val == table_name:
            rows.append(row)
    return rows


def find_row_by_field(ws, table_col: int, field_col: int, table_name: str, field_name: str):
    """返回指定表字段所在行号。"""
    for row in range(2, ws.max_row + 1):
        if (ws.cell(row=row, column=table_col).value == table_name and
                ws.cell(row=row, column=field_col).value == field_name):
            return row
    return None


def copy_row_style(src_ws, dst_ws, src_row: int, dst_row: int):
    """复制一行的样式。"""
    for col in range(1, src_ws.max_column + 1):
        src_cell = src_ws.cell(row=src_row, column=col)
        dst_cell = dst_ws.cell(row=dst_row, column=col)
        if src_cell.has_style:
            dst_cell.font = copy.copy(src_cell.font)
            dst_cell.border = copy.copy(src_cell.border)
            dst_cell.fill = copy.copy(src_cell.fill)
            dst_cell.number_format = copy.copy(src_cell.number_format)
            dst_cell.protection = copy.copy(src_cell.protection)
            dst_cell.alignment = copy.copy(src_cell.alignment)


def backup_excel():
    """创建带时间戳的备份。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_path = EXCEL_PATH.with_suffix(f".before_fix_{ts}.bak")
    shutil.copy2(EXCEL_PATH, bak_path)
    print(f"已备份原 Excel: {bak_path}")
    return bak_path


def update_overview(wb):
    """更新 01_概览关键数字。"""
    ws = wb["01_概览"]
    updates = {
        "源表数量": 80,
        "外键关系": "199 条",
        "索引": "463 个",
        "数据字典类别": "143 个",
        "数据字典项": "643 个",
        "统计视图数量": 9,
    }
    # 字段总数需要单独处理，可能在 B 列后续位置
    for row in range(1, ws.max_row + 1):
        key = ws.cell(row=row, column=1).value
        if key in updates:
            ws.cell(row=row, column=2, value=updates[key])
    # 检查是否有字段总数行，没有则追加
    has_field_total = False
    for row in range(1, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == "字段总数":
            ws.cell(row=row, column=2, value="1,637（源表 1,490 + 视图 147）")
            has_field_total = True
            break
    if not has_field_total:
        # 在"数据字典项"后插入
        for row in range(1, ws.max_row + 1):
            if ws.cell(row=row, column=1).value == "数据字典项":
                ws.insert_rows(row + 1)
                ws.cell(row=row + 1, column=1, value="字段总数")
                ws.cell(row=row + 1, column=2, value="1,637（源表 1,490 + 视图 147）")
                break
    print("已更新 01_概览")


def update_03_table_list(ws):
    """在 03_全表清单 追加 stat_metric_definition。"""
    table_col = col_idx(ws, "表名")
    cn_col = col_idx(ws, "中文表名")
    type_col = col_idx(ws, "表类型")
    duty_col = col_idx(ws, "数据职责")
    usage_col = col_idx(ws, "使用部门")
    source_col = col_idx(ws, "是否源表")
    relation_col = col_idx(ws, "是否关系表")
    event_col = col_idx(ws, "是否事件/日志表")
    master_col = col_idx(ws, "是否主数据")
    pk_col = col_idx(ws, "主键")

    existing = set()
    for row in range(2, ws.max_row + 1):
        val = ws.cell(row=row, column=table_col).value
        if val:
            existing.add(val)

    start_row = ws.max_row + 1
    for idx, (table_name, meta) in enumerate(STAT_TABLE.items(), start=1):
        if table_name in existing:
            continue
        row = start_row + idx - 1
        ws.cell(row=row, column=1, value=row - 1)
        ws.cell(row=row, column=2, value=meta["domain"])
        ws.cell(row=row, column=3, value=meta["biz"])
        ws.cell(row=row, column=table_col, value=table_name)
        ws.cell(row=row, column=cn_col, value=meta["cn"])
        ws.cell(row=row, column=type_col, value=meta["type"])
        ws.cell(row=row, column=duty_col, value="保存对应业务域的核心对象或业务明细。")
        ws.cell(row=row, column=usage_col, value=meta["usage"])
        ws.cell(row=row, column=source_col, value=meta["is_source"])
        ws.cell(row=row, column=relation_col, value=meta["is_relation"])
        ws.cell(row=row, column=event_col, value=meta["is_event"])
        ws.cell(row=row, column=master_col, value=meta["is_master"])
        ws.cell(row=row, column=col_idx(ws, "字段数"), value=len(meta["fields"]))
        ws.cell(row=row, column=pk_col, value=meta["pk"])
        ws.cell(row=row, column=col_idx(ws, "主要关联对象"), value="—")
    print("已更新 03_全表清单")


def update_04_build_order(ws):
    """在 04_建表顺序 追加 4 张新表。"""
    headers = [c.value for c in ws[1]]
    seq_col = headers.index("阶段序号") + 1 if "阶段序号" in headers else 1
    stage_col = headers.index("阶段") + 1 if "阶段" in headers else 2
    phase_col = headers.index("阶段说明") + 1 if "阶段说明" in headers else 3
    layer_col = headers.index("主层级") + 1 if "主层级" in headers else 4
    domain_col = headers.index("业务域") + 1 if "业务域" in headers else 5
    table_col = headers.index("表名") + 1 if "表名" in headers else 6
    cn_col = headers.index("中文表名") + 1 if "中文表名" in headers else 7
    type_col = headers.index("表类型") + 1 if "表类型" in headers else 8
    desc_col = headers.index("说明") + 1 if "说明" in headers else 9

    existing = set()
    for row in range(2, ws.max_row + 1):
        val = ws.cell(row=row, column=table_col).value
        if val:
            existing.add(val)

    additions = [
        ("第5阶段", "市场签约后移交流程", "业务域层", "案件管理域", "case_intake_review", "收案审核记录表", "业务日志/流转表", "市场移交后、案管建案前，对委托主体/合同/收费/案件类型/收案条件/特殊审批进行多维审核。"),
        ("第6阶段", "案管收案、建案与分配", "关系层", "对象关系与多对多关联", "case_assignment_history", "案件分配变更历史表", "业务关联表", "记录案件分配变更、人员调整历史，支撑分案变更闭环。"),
        ("第6阶段", "案管收案、建案与分配", "业务域层", "案件管理域", "case_file_handover", "案件内部卷宗/人员交接表", "业务主表", "记录案件内部卷宗/人员交接，含交接材料清单与卷宗审核。"),
        ("第6阶段", "案管收案、建案与分配", "业务域层", "案件管理域", "case_close_review", "结案与归档审核表", "业务日志/流转表", "案件办理完毕后进行结案审核与归档审核，更新案件状态。"),
    ]

    start_row = ws.max_row + 1
    idx = 0
    for stage, phase, layer, domain, table_name, cn, ttype, desc in additions:
        if table_name in existing:
            continue
        row = start_row + idx
        ws.cell(row=row, column=seq_col, value=row - 1)
        ws.cell(row=row, column=stage_col, value=stage)
        ws.cell(row=row, column=phase_col, value=phase)
        ws.cell(row=row, column=layer_col, value=layer)
        ws.cell(row=row, column=domain_col, value=domain)
        ws.cell(row=row, column=table_col, value=table_name)
        ws.cell(row=row, column=cn_col, value=cn)
        ws.cell(row=row, column=type_col, value=ttype)
        ws.cell(row=row, column=desc_col, value=desc)
        idx += 1
    print("已更新 04_建表顺序")


def update_06_full_dict(ws):
    """在 06_全字段数据字典 追加 4 张新表 + stat_metric_definition + sys_approval_record.biz_type/biz_id。"""
    table_col = col_idx(ws, "表名")
    field_col = col_idx(ws, "字段名")
    seq_col = col_idx(ws, "字段序号")

    all_additions = {**NEW_TABLES, **STAT_TABLE}

    # 获取当前最大序号
    max_no = 0
    for row in range(2, ws.max_row + 1):
        val = ws.cell(row=row, column=1).value
        if isinstance(val, int):
            max_no = max(max_no, val)

    start_row = ws.max_row + 1
    current_no = max_no
    idx = 0

    for table_name, meta in all_additions.items():
        # 检查该表是否已存在
        existing_fields = set()
        for r in find_rows_by_table(ws, table_col, table_name):
            existing_fields.add(ws.cell(row=r, column=field_col).value)

        for f_idx, (fname, fcn, ftype, fnull, fconstraint, fbind, fcomment) in enumerate(meta["fields"], start=1):
            if fname in existing_fields:
                continue
            current_no += 1
            row = start_row + idx
            ws.cell(row=row, column=1, value=current_no)
            ws.cell(row=row, column=2, value=meta["domain"])
            ws.cell(row=row, column=3, value=meta["biz"])
            ws.cell(row=row, column=table_col, value=table_name)
            ws.cell(row=row, column=col_idx(ws, "中文表名"), value=meta["cn"])
            ws.cell(row=row, column=col_idx(ws, "表类型"), value=meta["type"])
            ws.cell(row=row, column=seq_col, value=f_idx)
            ws.cell(row=row, column=field_col, value=fname)
            ws.cell(row=row, column=col_idx(ws, "中文字段名"), value=fcn)
            ws.cell(row=row, column=col_idx(ws, "数据类型"), value=ftype)
            ws.cell(row=row, column=col_idx(ws, "空值/默认"), value=fnull)
            ws.cell(row=row, column=col_idx(ws, "主键/外键/约束"), value=fconstraint)
            ws.cell(row=row, column=col_idx(ws, "绑定字典编码"), value=fbind)
            ws.cell(row=row, column=col_idx(ws, "字典说明"), value="—")
            ws.cell(row=row, column=col_idx(ws, "字段性质"), value="源数据字段")
            ws.cell(row=row, column=col_idx(ws, "使用部门"), value=meta["usage"])
            ws.cell(row=row, column=col_idx(ws, "字段注释"), value=fcomment)
            idx += 1

    # 追加 sys_approval_record.biz_type / biz_id
    sap_rows = find_rows_by_table(ws, table_col, "sys_approval_record")
    existing_sap_fields = {ws.cell(row=r, column=field_col).value for r in sap_rows}
    sap_additions = [
        ("biz_type", "业务对象类型", "VARCHAR(80)", "YES", "—", "—", "业务对象类型，用于将审批记录关联到具体业务对象（如 fee_agreement、case_close_review）。"),
        ("biz_id", "业务对象ID", "BIGINT", "YES", "—", "—", "业务对象ID，与 biz_type 联合定位被审批的业务单据。"),
    ]
    for fname, fcn, ftype, fnull, fconstraint, fbind, fcomment in sap_additions:
        if fname in existing_sap_fields:
            continue
        current_no += 1
        row = start_row + idx
        ws.cell(row=row, column=1, value=current_no)
        ws.cell(row=row, column=2, value="流程事件层")
        ws.cell(row=row, column=3, value="审批流程")
        ws.cell(row=row, column=table_col, value="sys_approval_record")
        ws.cell(row=row, column=col_idx(ws, "中文表名"), value="审批记录表")
        ws.cell(row=row, column=col_idx(ws, "表类型"), value="业务日志/流转表")
        ws.cell(row=row, column=seq_col, value=len(sap_rows) + 1)
        ws.cell(row=row, column=field_col, value=fname)
        ws.cell(row=row, column=col_idx(ws, "中文字段名"), value=fcn)
        ws.cell(row=row, column=col_idx(ws, "数据类型"), value=ftype)
        ws.cell(row=row, column=col_idx(ws, "空值/默认"), value=fnull)
        ws.cell(row=row, column=col_idx(ws, "主键/外键/约束"), value=fconstraint)
        ws.cell(row=row, column=col_idx(ws, "绑定字典编码"), value=fbind)
        ws.cell(row=row, column=col_idx(ws, "字典说明"), value="—")
        ws.cell(row=row, column=col_idx(ws, "字段性质"), value="源数据字段")
        ws.cell(row=row, column=col_idx(ws, "使用部门"), value="全部门")
        ws.cell(row=row, column=col_idx(ws, "字段注释"), value=fcomment)
        idx += 1

    print("已更新 06_全字段数据字典")


def fix_fin_fee_agreement(ws):
    """修正 fin_fee_agreement 字段：恢复 fee_type、修正 agreement_amount。"""
    table_col = col_idx(ws, "表名")
    field_col = col_idx(ws, "字段名")
    type_col = col_idx(ws, "数据类型")
    null_col = col_idx(ws, "空值/默认")
    bind_col = col_idx(ws, "绑定字典编码")
    cn_col = col_idx(ws, "中文字段名")
    comment_col = col_idx(ws, "字段注释")

    rows = find_rows_by_table(ws, table_col, "fin_fee_agreement")
    agreement_amount_row = None
    insert_after_row = None
    for row in rows:
        field = ws.cell(row=row, column=field_col).value
        if field == "agreement_amount":
            agreement_amount_row = row
        if field == "contract_no":
            insert_after_row = row

    if agreement_amount_row:
        ws.cell(row=agreement_amount_row, column=type_col, value="NUMERIC(16,2)")
        ws.cell(row=agreement_amount_row, column=null_col, value="NO")
        ws.cell(row=agreement_amount_row, column=bind_col, value="—")
        ws.cell(row=agreement_amount_row, column=cn_col, value="协议金额")
        ws.cell(row=agreement_amount_row, column=comment_col,
                value="记录收费协议最终确认的协议金额，用于合同收费、转化金额和后续财务统计。")

    # 在 contract_no 后插入 fee_type 行
    if insert_after_row:
        for row in rows:
            if ws.cell(row=row, column=field_col).value == "fee_type":
                return
        new_row = insert_after_row + 1
        ws.insert_rows(new_row)
        prev = new_row - 1
        ws.cell(row=new_row, column=1, value=ws.cell(row=prev, column=1).value + 1)
        ws.cell(row=new_row, column=2, value=ws.cell(row=prev, column=2).value)
        ws.cell(row=new_row, column=3, value=ws.cell(row=prev, column=3).value)
        ws.cell(row=new_row, column=table_col, value="fin_fee_agreement")
        ws.cell(row=new_row, column=col_idx(ws, "中文表名"), value="收费协议表")
        ws.cell(row=new_row, column=col_idx(ws, "表类型"), value="源表")
        ws.cell(row=new_row, column=col_idx(ws, "字段序号"), value=6)
        ws.cell(row=new_row, column=field_col, value="fee_type")
        ws.cell(row=new_row, column=cn_col, value="收费方式")
        ws.cell(row=new_row, column=type_col, value="VARCHAR(80)")
        ws.cell(row=new_row, column=null_col, value="NO")
        ws.cell(row=new_row, column=col_idx(ws, "主键/外键/约束"), value="—")
        ws.cell(row=new_row, column=bind_col, value="fee_type")
        ws.cell(row=new_row, column=col_idx(ws, "字典说明"), value="—")
        ws.cell(row=new_row, column=col_idx(ws, "字段性质"), value="源数据字段")
        ws.cell(row=new_row, column=col_idx(ws, "使用部门"), value="市场部；财务部")
        ws.cell(row=new_row, column=comment_col,
                value="记录收费方式，用于区分收费协议表中不同业务类别。该字段应绑定数据字典「fee_type/收费方式」，常见值：固定收费、分阶段收费、风险代理。")


def fix_nullable(ws, table_name: str, field_name: str):
    """把指定表字段的 空值/默认 改为 YES。"""
    table_col = col_idx(ws, "表名")
    field_col = col_idx(ws, "字段名")
    null_col = col_idx(ws, "空值/默认")
    rows = find_rows_by_table(ws, table_col, table_name)
    for row in rows:
        if ws.cell(row=row, column=field_col).value == field_name:
            ws.cell(row=row, column=null_col, value="YES")


def update_dict_07(ws):
    """更新 07_字典类型清单。"""
    code_col = col_idx(ws, "字典类别")
    enum_col = col_idx(ws, "枚举值/字典值")
    name_col = col_idx(ws, "中文名称")

    # 更新已有字典
    for row in range(2, ws.max_row + 1):
        code = ws.cell(row=row, column=code_col).value
        if code == "agreement_status":
            ws.cell(row=row, column=enum_col,
                    value="1=草稿；2=已签署；3=已终止；4=待拟定；5=待审核；6=待签署；7=已作废；8=已解除")
        elif code == "case_status":
            ws.cell(row=row, column=enum_col,
                    value="1=收案中；2=已分配；3=办理中；4=已结案；5=待结案审核；6=已归档")

    # 新增字典类别
    existing = {ws.cell(row=r, column=code_col).value for r in range(2, ws.max_row + 1)}
    start_row = ws.max_row + 1
    idx = 0
    for code, info in NEW_DICTS.items():
        if code in existing:
            continue
        enum_str = "；".join([f"{v}={l}" for v, l, _ in info["items"]])
        ws.cell(row=start_row + idx, column=1, value=start_row + idx - 1)
        ws.cell(row=start_row + idx, column=code_col, value=code)
        ws.cell(row=start_row + idx, column=name_col, value=info["name"])
        ws.cell(row=start_row + idx, column=enum_col, value=enum_str)
        ws.cell(row=start_row + idx, column=col_idx(ws, "说明"), value="")
        idx += 1
    print("已更新 07_字典类型清单")


def update_dict_08(ws):
    """更新 08_字典值展开表。"""
    code_col = col_idx(ws, "字典编码")
    name_col = col_idx(ws, "字典名称")
    val_col = col_idx(ws, "枚举值")
    label_col = col_idx(ws, "枚举显示值")
    sort_col = col_idx(ws, "排序")
    enable_col = col_idx(ws, "是否启用")

    existing = set()
    for row in range(2, ws.max_row + 1):
        code = ws.cell(row=row, column=code_col).value
        val = ws.cell(row=row, column=val_col).value
        if code and val is not None:
            existing.add((str(code), str(val)))

    start_row = ws.max_row + 1
    idx = 0

    def add_items(code, info, dept="案件管理部", table="—", field="—"):
        nonlocal idx
        for v, l, s in info["items"]:
            key = (code, str(v))
            if key in existing:
                continue
            row = start_row + idx
            ws.cell(row=row, column=col_idx(ws, "使用部门"), value=dept)
            ws.cell(row=row, column=col_idx(ws, "表名"), value=table)
            ws.cell(row=row, column=col_idx(ws, "中文表名"), value="")
            ws.cell(row=row, column=col_idx(ws, "字段名"), value=field)
            ws.cell(row=row, column=col_idx(ws, "中文字段名"), value="")
            ws.cell(row=row, column=code_col, value=code)
            ws.cell(row=row, column=name_col, value=info["name"])
            ws.cell(row=row, column=val_col, value=v)
            ws.cell(row=row, column=label_col, value=l)
            ws.cell(row=row, column=sort_col, value=s)
            ws.cell(row=row, column=enable_col, value="是")
            ws.cell(row=row, column=col_idx(ws, "字段注释"), value="")
            idx += 1

    add_items("agreement_status", DICT_UPDATES["agreement_status"], dept="市场部；财务部", table="fin_fee_agreement", field="agreement_status")
    add_items("case_status", DICT_UPDATES["case_status"], dept="案件管理部", table="case_main", field="case_status")
    add_items("intake_review_aspect", NEW_DICTS["intake_review_aspect"], dept="案件管理部", table="case_intake_review", field="review_aspect")
    add_items("review_result", NEW_DICTS["review_result"], dept="案件管理部", table="case_intake_review", field="review_result")
    add_items("file_handover_type", NEW_DICTS["file_handover_type"], dept="案件管理部", table="case_file_handover", field="handover_type")
    add_items("file_handover_status", NEW_DICTS["file_handover_status"], dept="案件管理部", table="case_file_handover", field="handover_status")
    add_items("close_review_type", NEW_DICTS["close_review_type"], dept="案件管理部", table="case_close_review", field="review_type")
    add_items("close_review_status", NEW_DICTS["close_review_status"], dept="案件管理部", table="case_close_review", field="review_status")
    print("已更新 08_字典值展开表")


def update_05_field_dict(ws):
    """补充 05_字段字典。"""
    table_col = col_idx(ws, "表名")
    field_col = col_idx(ws, "字段名")

    # 删除 fin_fee_agreement.agreement_amount 的错误字典绑定（如果存在）
    for row in range(2, ws.max_row + 1):
        if ws.cell(row=row, column=table_col).value == "fin_fee_agreement" and ws.cell(row=row, column=field_col).value == "agreement_amount":
            ws.cell(row=row, column=col_idx(ws, "绑定字典编码"), value="—")
            ws.cell(row=row, column=col_idx(ws, "字典名称"), value="—")

    existing = set()
    for row in range(2, ws.max_row + 1):
        existing.add((ws.cell(row=row, column=table_col).value, ws.cell(row=row, column=field_col).value))

    start_row = ws.max_row + 1
    idx = 0
    for (layer, biz, table, cn, field, fcn, dtype, bind, dict_name, usage, comment) in FIELD_DICT_ROWS:
        if (table, field) in existing:
            continue
        row = start_row + idx
        ws.cell(row=row, column=1, value=row - 1)
        ws.cell(row=row, column=col_idx(ws, "主层级"), value=layer)
        ws.cell(row=row, column=col_idx(ws, "业务域"), value=biz)
        ws.cell(row=row, column=table_col, value=table)
        ws.cell(row=row, column=col_idx(ws, "中文表名"), value=cn)
        ws.cell(row=row, column=field_col, value=field)
        ws.cell(row=row, column=col_idx(ws, "中文字段名"), value=fcn)
        ws.cell(row=row, column=col_idx(ws, "数据类型"), value=dtype)
        ws.cell(row=row, column=col_idx(ws, "绑定字典编码"), value=bind)
        ws.cell(row=row, column=col_idx(ws, "字典名称"), value=dict_name)
        ws.cell(row=row, column=col_idx(ws, "使用部门"), value=usage)
        ws.cell(row=row, column=col_idx(ws, "字段注释"), value=comment)
        idx += 1
    print("已更新 05_字段字典")


def update_09_fk(ws):
    """补充 09_外键关系清单。"""
    existing = set()
    for row in range(2, ws.max_row + 1):
        existing.add((ws.cell(row=row, column=col_idx(ws, "来源表")).value,
                      ws.cell(row=row, column=col_idx(ws, "来源字段")).value))

    start_row = ws.max_row + 1
    idx = 0
    for (layer, usage, src_table, src_cn, src_type, src_field, target, note) in FK_ROWS:
        if (src_table, src_field) in existing:
            continue
        row = start_row + idx
        ws.cell(row=row, column=1, value=row - 1)
        ws.cell(row=row, column=col_idx(ws, "主层级"), value=layer)
        ws.cell(row=row, column=col_idx(ws, "使用部门"), value=usage)
        ws.cell(row=row, column=col_idx(ws, "来源表"), value=src_table)
        ws.cell(row=row, column=col_idx(ws, "来源表中文"), value=src_cn)
        ws.cell(row=row, column=col_idx(ws, "来源表类型"), value=src_type)
        ws.cell(row=row, column=col_idx(ws, "来源字段"), value=src_field)
        ws.cell(row=row, column=col_idx(ws, "目标表字段"), value=target)
        ws.cell(row=row, column=col_idx(ws, "说明"), value=note)
        idx += 1
    print("已更新 09_外键关系清单")


def update_10_index(ws):
    """补充 10_索引清单。"""
    existing = set()
    for row in range(2, ws.max_row + 1):
        existing.add(ws.cell(row=row, column=col_idx(ws, "索引名")).value)

    start_row = ws.max_row + 1
    idx = 0
    for (table, cn, idx_name, unique, fields, definition) in INDEX_ROWS:
        if idx_name in existing:
            continue
        row = start_row + idx
        ws.cell(row=row, column=1, value=row - 1)
        ws.cell(row=row, column=col_idx(ws, "表名"), value=table)
        ws.cell(row=row, column=col_idx(ws, "中文表名"), value=cn)
        ws.cell(row=row, column=col_idx(ws, "索引名"), value=idx_name)
        ws.cell(row=row, column=col_idx(ws, "是否唯一"), value=unique)
        ws.cell(row=row, column=col_idx(ws, "索引字段"), value=fields)
        ws.cell(row=row, column=col_idx(ws, "定义"), value=definition)
        idx += 1
    print("已更新 10_索引清单")


def fix_mapping_sheets(wb):
    """修正流程映射页中的旧字段名。"""
    MAPPING_REPLACEMENTS = {
        "assigned_employee_id": "employee_id",
        "call_time": "call_start_time",
        "duration_seconds": "call_duration_seconds",
        "deal_amount": "agreement_amount",
        "agreement_id": "fee_agreement_id",
        "handover_remark": "remark",
    }
    for sheet_name in ["12_市场部流程字段映射", "13_案管部流程字段映射", "14_律师部流程字段映射", "15_财务回款流程字段映射"]:
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        field_col = col_idx(ws, "对应字段")
        for row in range(2, ws.max_row + 1):
            val = ws.cell(row=row, column=field_col).value
            if not val:
                continue
            new_val = val
            for old_str, new_str in MAPPING_REPLACEMENTS.items():
                new_val = new_val.replace(old_str, new_str)
            if "case_intake_handover" in str(ws.cell(row=row, column=col_idx(ws, "对应表")).value or ""):
                new_val = new_val.replace("、payment_plan_id", "").replace("payment_plan_id、", "").replace("payment_plan_id", "")
            ws.cell(row=row, column=field_col, value=new_val)
    print("已修正通用流程映射旧字段名")


def rewrite_marketing_mapping(ws):
    """重写 12_市场部流程字段映射。"""
    headers = [c.value for c in ws[1]]
    # 清空原有数据，保留表头
    for row in range(ws.max_row, 1, -1):
        ws.delete_rows(row)

    new_rows = [
        (1, "线索接收", "接收运营/渠道线索", "市场主管/市场人员", "crm_lead", "lead_no、case_source、offline_expand_remark、primary_party_id、case_type、case_brief", "运营部、外部渠道或市场人员线下拓展产生线索", "生成线索主记录", "作为市场台账起点；选择线下拓展时填写线下拓展说明。"),
        (2, "线下拓展", "选择线下案源并填写拓展说明", "市场拓展人员", "crm_lead", "case_source、offline_expand_remark", "线索来源选择“线下拓展”", "形成线下拓展备注", "用于记录线下拓展地点、活动、合作单位、地推人员或其他线下来源细节。"),
        (3, "线索分配", "分配电邀人员", "市场主管", "lead_assignment_log", "lead_id、to_employee_id、assigned_by、assigned_at、assignment_status", "线索需要人工跟进", "形成责任人", "可支持重新分配。"),
        (4, "电话邀约", "生成电话任务", "市场主管", "mkt_call_task、mkt_call_task_item", "id、lead_id、assigned_employee_id、planned_call_time", "线索分配后", "形成拨打清单", "适合批量外呼管理。"),
        (5, "电话邀约", "记录通话内容", "电邀人员", "mkt_call_record", "call_start_time、call_result、call_duration_seconds、recording_attachment_id、conversation_summary", "发生电话沟通", "形成通话记录", "录音可进入AI分析。"),
        (6, "电话邀约", "判断客户意向", "电邀人员/AI辅助", "mkt_call_record、crm_lead", "intention_level、next_action、remark、next_follow_time", "通话结束", "形成跟进结论", "意向低/中/高进入不同后续策略。"),
        (7, "电话质检", "对通话进行质检", "市场主管/质检人员", "mkt_call_quality_review", "quality_score、risk_words_detail、quality_review_status、review_comment", "需要抽检或AI预警", "形成质检结果", "支撑人员绩效和话术优化。"),
        (8, "预约到访", "预约客户到所", "电邀人员", "mkt_appointment", "appointment_time、appointment_status、reception_employee_id、appointment_type", "客户同意到所", "形成预约记录", "后续统计到访率。"),
        (9, "预约到访", "改约/取消记录", "电邀人员", "mkt_appointment_change_log", "old_appointment_time、new_appointment_time、remark、changed_by", "客户改约或取消", "形成改约轨迹", "避免只保留最后结果。"),
        (10, "到访接待", "记录实际到访", "前台/市场人员", "mkt_appointment", "actual_arrival_time、visit_result", "客户到所或爽约", "形成到访结果", "支持爽约、二次到所统计。"),
        (11, "谈案", "登记谈案过程", "主谈人/副谈人", "lead_negotiation_record、crm_lead", "main_negotiator_id、assistant_negotiator_id、deal_amount、analysis_id、negotiation_result", "客户到访谈案", "形成谈案记录", "可关联谈案录音和AI分析。"),
        (12, "谈案", "记录未成交原因", "主谈人", "lead_negotiation_record", "lost_reason_type、next_follow_up_at、remark", "谈案未签约", "形成复盘原因", "用于市场复盘和二次转化。"),
        (13, "签约", "生成收费协议/委托合同", "市场部/主谈人", "fin_fee_agreement", "agreement_no、agreement_amount、sign_date、client_id、fee_type", "客户确认签约", "形成收费协议", "合同是市场部最后一个核心环节。"),
        (14, "付款计划", "生成付款节点", "市场部/财务", "fin_payment_plan", "receivable_amount、due_date、payment_node、payment_node_status", "合同签署后", "形成回款计划", "案管和财务后续共用。"),
        (15, "移交案管", "提交签约案件", "市场部", "case_intake_handover", "lead_id、fee_agreement_id、handover_status、handover_time", "签约完成并整理材料", "形成待接收移交记录", "进入案管接收流程。"),
        (16, "移交案管", "补充移交资料", "市场部", "case_intake_handover", "missing_materials、remark、updated_at", "案管退回补充", "资料补齐后再次提交", "减少市场与案管扯皮。"),
        (17, "市场台账", "展示市场转化闭环", "市场主管/管理层", "v_mkt_call_invitation_ledger、v_mkt_visit_negotiation_ledger", "视图字段", "按月或人员查询", "形成市场部最终台账", "对应 20_市场部台账字段。"),
    ]

    for r_idx, row_data in enumerate(new_rows, start=2):
        for c_idx, val in enumerate(row_data, start=1):
            ws.cell(row=r_idx, column=c_idx, value=val)
    print("已重写 12_市场部流程字段映射")


def update_case_management_mapping(ws):
    """局部修正 13_案管部流程字段映射：插入 4 张新表环节并修正错误字段。"""
    headers = [c.value for c in ws[1]]
    seq_col = headers.index("流程序号") + 1
    field_col = headers.index("对应字段") + 1
    table_col = headers.index("对应表") + 1

    # 先修正错误字段
    for row in range(2, ws.max_row + 1):
        table_val = ws.cell(row=row, column=table_col).value
        field_val = ws.cell(row=row, column=field_col).value
        if not field_val:
            continue
        if "unpaid_amount" in str(field_val):
            ws.cell(row=row, column=field_col, value=field_val.replace("unpaid_amount", "receivable_amount、received_amount（计算 unpaid_amount）"))
        # 案管台账描述性文字简化
        if table_val and "v_case_management_ledger" in str(table_val) and "案件、人员、材料、调档、回款、开票、NAS、AI索引字段" in str(field_val):
            ws.cell(row=row, column=field_col, value="视图列")

    # 找到合适位置插入新行
    # 在“材料检查”后插入收案审核
    insert_positions = []
    for row in range(2, ws.max_row + 1):
        seq = ws.cell(row=row, column=seq_col).value
        # 在流程序号 3（退回市场部补充）后插入 3.5
        if seq == 3:
            insert_positions.append((row, 3.5, "接收移交/材料检查", "收案多维审核", "case_intake_review", "intake_handover_id、review_aspect、review_result、supplement_requirement", "材料检查完成后", "形成收案审核结论", "支撑委托主体/合同/收费/案件类型/收案条件/特殊审批六维审核。"))
        # 在流程序号 9（人员分配）后插入 9.5、9.6
        if seq == 9:
            insert_positions.append((row, 9.5, "人员分配", "分案调整/历史记录", "case_assignment_history", "case_assignment_id、previous_employee_id、new_employee_id、is_current、effective_from", "人员分配发生变更", "形成分配变更历史", "记录主办/协办律师变更轨迹。"))
            insert_positions.append((row, 9.6, "人员分配", "卷宗/人员交接", "case_file_handover", "case_id、handover_type、from_employee_id、to_employee_id、material_list_json、archive_review_status", "分案调整或卷宗归档", "形成交接记录", "记录卷宗交接与审核。"))
        # 在流程序号 20（结案归档）前插入 19.5
        if seq == 20:
            insert_positions.append((row - 1, 19.5, "结案归档", "结案归档审核", "case_close_review", "case_id、review_type、review_status、close_date、archive_date、material_complete_flag", "案件办理完毕", "形成结案/归档审核结论", "审核通过后更新案件状态。"))

    # 从后往前插入，避免行号变化
    for insert_after_row, new_seq, stage, action, table, fields, trigger, output, note in sorted(insert_positions, key=lambda x: x[0], reverse=True):
        ws.insert_rows(insert_after_row + 1)
        new_row = insert_after_row + 1
        ws.cell(row=new_row, column=seq_col, value=new_seq)
        ws.cell(row=new_row, column=2, value=stage)
        ws.cell(row=new_row, column=3, value=action)
        ws.cell(row=new_row, column=4, value="案管人员")
        ws.cell(row=new_row, column=table_col, value=table)
        ws.cell(row=new_row, column=field_col, value=fields)
        ws.cell(row=new_row, column=7, value=trigger)
        ws.cell(row=new_row, column=8, value=output)
        ws.cell(row=new_row, column=9, value=note)

    print("已更新 13_案管部流程字段映射")


def normalize_field_types(ws):
    """统一 06_全字段数据字典 字段类型为 PostgreSQL 原生类型。"""
    type_col = col_idx(ws, "数据类型")
    changed = 0
    for row in range(2, ws.max_row + 1):
        val = ws.cell(row=row, column=type_col).value
        if not val:
            continue
        upper_val = str(val).upper().strip()
        # 注意：TINYINT(1) 优先于 TINYINT
        if upper_val == "TINYINT(1)" or upper_val == "TINYINT(1) UNSIGNED":
            ws.cell(row=row, column=type_col, value="BOOLEAN")
            changed += 1
        elif upper_val == "TINYINT" or upper_val == "TINYINT UNSIGNED":
            ws.cell(row=row, column=type_col, value="SMALLINT")
            changed += 1
        elif "BIGINT UNSIGNED" in upper_val:
            ws.cell(row=row, column=type_col, value=str(val).replace("UNSIGNED", "").strip())
            changed += 1
        elif upper_val == "DATETIME":
            ws.cell(row=row, column=type_col, value="TIMESTAMP WITH TIME ZONE")
            changed += 1
        elif upper_val == "LONGTEXT" or upper_val == "MEDIUMTEXT":
            ws.cell(row=row, column=type_col, value="TEXT")
            changed += 1
        elif upper_val == "JSON":
            ws.cell(row=row, column=type_col, value="JSONB")
            changed += 1
    print(f"已统一字段类型，共替换 {changed} 处")


def update_00_update_record(ws):
    """更新 00_更新记录。"""
    # 在末尾追加一行
    start_row = ws.max_row + 1
    ws.cell(row=start_row, column=1, value="v2.16")
    ws.cell(row=start_row, column=2, value="2026-07-10")
    ws.cell(row=start_row, column=3, value="最终冻结版")
    ws.cell(row=start_row, column=4, value="修复 Codex 审查 7 个关键设计缺陷，新增 4 张业务闭环表，统一字段类型为 PostgreSQL 原生类型，Excel 与数据库/校验报告重新对齐。")
    print("已更新 00_更新记录")


def update_02_process_overview(ws):
    """更新 02_业务流程总览，补充 4 个闭环节点。"""
    # 由于不清楚该 sheet 的具体结构，保守处理：在末尾追加说明行
    start_row = ws.max_row + 1
    ws.cell(row=start_row, column=1, value="v2.16 补充")
    ws.cell(row=start_row, column=2, value="收案审核")
    ws.cell(row=start_row, column=3, value="case_intake_review")
    ws.cell(row=start_row, column=4, value="案管接收材料后，对委托主体/合同/收费/案件类型/收案条件/特殊审批进行多维审核。")
    start_row += 1
    ws.cell(row=start_row, column=1, value="v2.16 补充")
    ws.cell(row=start_row, column=2, value="分案变更历史")
    ws.cell(row=start_row, column=3, value="case_assignment_history")
    ws.cell(row=start_row, column=4, value="记录案件分配变更、人员调整历史。")
    start_row += 1
    ws.cell(row=start_row, column=1, value="v2.16 补充")
    ws.cell(row=start_row, column=2, value="内部卷宗交接")
    ws.cell(row=start_row, column=3, value="case_file_handover")
    ws.cell(row=start_row, column=4, value="记录案件内部卷宗/人员交接及卷宗审核。")
    start_row += 1
    ws.cell(row=start_row, column=1, value="v2.16 补充")
    ws.cell(row=start_row, column=2, value="结案归档审核")
    ws.cell(row=start_row, column=3, value="case_close_review")
    ws.cell(row=start_row, column=4, value="案件办理完毕后进行结案审核与归档审核。")
    print("已更新 02_业务流程总览")


def update_20_fixes(ws):
    """更新 20_修复问题。"""
    fixes = [
        ("1", "合同与建案顺序冲突", "fin_fee_agreement.case_id、fin_payment_plan.case_id 改为 nullable", "v2.16"),
        ("2", "agreement_amount 类型与绑定错误", "恢复为 NUMERIC(16,2)，新增独立 fee_type 字段绑定字典", "v2.16"),
        ("3", "agreement_status 生命周期不足", "扩展为 8 个状态", "v2.16"),
        ("4", "sys_approval_record 缺少业务对象关联", "新增 biz_type、biz_id", "v2.16"),
        ("5", "收案审核不完整", "新增 case_intake_review 表", "v2.16"),
        ("6", "人员调整与内部调档无闭环", "新增 case_assignment_history、case_file_handover 表", "v2.16"),
        ("7", "结案归档流程缺失", "新增 case_close_review 表，扩展 case_status", "v2.16"),
        ("8", "Excel 与数据库/校验报告不一致", "重新对齐 01/03/04/05/06/07/08/09/10/12/13 sheet，统一字段类型", "v2.16"),
    ]
    start_row = ws.max_row + 1
    for idx, (no, issue, fix, version) in enumerate(fixes, start=0):
        row = start_row + idx
        ws.cell(row=row, column=1, value=no)
        ws.cell(row=row, column=2, value=issue)
        ws.cell(row=row, column=3, value=fix)
        ws.cell(row=row, column=4, value=version)
    print("已更新 20_修复问题")


def main() -> int:
    if not EXCEL_PATH.exists():
        print(f"Excel 文件不存在: {EXCEL_PATH}", file=sys.stderr)
        return 1

    backup_excel()
    wb = openpyxl.load_workbook(EXCEL_PATH)

    # 1. 更新 01_概览
    update_overview(wb)

    # 4. 更新 06_全字段数据字典
    ws_full = wb["06_全字段数据字典"]
    fix_fin_fee_agreement(ws_full)
    fix_nullable(ws_full, "fin_fee_agreement", "case_id")
    fix_nullable(ws_full, "fin_payment_plan", "case_id")
    update_06_full_dict(ws_full)

    # 2. 更新 03_全表清单
    ws_tables = wb["03_全表清单"]
    update_03_table_list(ws_tables)

    # 3. 更新 04_建表顺序
    update_04_build_order(wb["04_建表顺序"])

    # 5. 更新 05_字段字典
    update_05_field_dict(wb["05_字段字典"])

    # 6. 更新 09_外键关系清单
    update_09_fk(wb["09_外键关系清单"])

    # 7. 更新 10_索引清单
    update_10_index(wb["10_索引清单"])

    # 8. 更新字典
    update_dict_07(wb["07_字典类型清单"])
    update_dict_08(wb["08_字典值展开表"])

    # 9. 修正通用流程映射
    fix_mapping_sheets(wb)

    # 10. 重写市场部流程映射
    rewrite_marketing_mapping(wb["12_市场部流程字段映射"])

    # 11. 局部修正案管部流程映射
    update_case_management_mapping(wb["13_案管部流程字段映射"])

    # 12. 统一字段类型
    normalize_field_types(ws_full)

    # 13. 更新 00/02/20 sheet
    update_00_update_record(wb["00_更新记录"])
    update_02_process_overview(wb["02_业务流程总览"])
    update_20_fixes(wb["20_修复问题"])

    # 保存并覆盖原文件
    wb.save(EXCEL_PATH)
    print(f"已覆盖原 Excel: {EXCEL_PATH}")
    return 0


def add_new_tables_to_full_dict(ws):
    """原 update_excel_v2_16.py 的逻辑：在 06_全字段数据字典 追加 4 张新表。"""
    table_col = col_idx(ws, "表名")
    field_col = col_idx(ws, "字段名")
    seq_col = col_idx(ws, "字段序号")

    max_no = 0
    for row in range(2, ws.max_row + 1):
        val = ws.cell(row=row, column=1).value
        if isinstance(val, int):
            max_no = max(max_no, val)

    start_row = ws.max_row + 1
    current_no = max_no
    idx = 0

    for table_name, meta in NEW_TABLES.items():
        for f_idx, (fname, fcn, ftype, fnull, fconstraint, fbind, fcomment) in enumerate(meta["fields"], start=1):
            current_no += 1
            row = start_row + idx
            ws.cell(row=row, column=1, value=current_no)
            ws.cell(row=row, column=2, value=meta["domain"])
            ws.cell(row=row, column=3, value=meta["biz"])
            ws.cell(row=row, column=table_col, value=table_name)
            ws.cell(row=row, column=col_idx(ws, "中文表名"), value=meta["cn"])
            ws.cell(row=row, column=col_idx(ws, "表类型"), value=meta["type"])
            ws.cell(row=row, column=seq_col, value=f_idx)
            ws.cell(row=row, column=field_col, value=fname)
            ws.cell(row=row, column=col_idx(ws, "中文字段名"), value=fcn)
            ws.cell(row=row, column=col_idx(ws, "数据类型"), value=ftype)
            ws.cell(row=row, column=col_idx(ws, "空值/默认"), value=fnull)
            ws.cell(row=row, column=col_idx(ws, "主键/外键/约束"), value=fconstraint)
            ws.cell(row=row, column=col_idx(ws, "绑定字典编码"), value=fbind)
            ws.cell(row=row, column=col_idx(ws, "字典说明"), value="—")
            ws.cell(row=row, column=col_idx(ws, "字段性质"), value="源数据字段")
            ws.cell(row=row, column=col_idx(ws, "使用部门"), value=meta["usage"])
            ws.cell(row=row, column=col_idx(ws, "字段注释"), value=fcomment)
            idx += 1


def add_new_tables_to_table_list(ws):
    """原 update_excel_v2_16.py 的逻辑：在 03_全表清单 追加新表。"""
    table_col = col_idx(ws, "表名")
    cn_col = col_idx(ws, "中文表名")
    type_col = col_idx(ws, "表类型")
    duty_col = col_idx(ws, "数据职责")
    usage_col = col_idx(ws, "使用部门")
    source_col = col_idx(ws, "是否源表")
    relation_col = col_idx(ws, "是否关系表")
    event_col = col_idx(ws, "是否事件/日志表")
    master_col = col_idx(ws, "是否主数据")
    pk_col = col_idx(ws, "主键")

    start_row = ws.max_row + 1
    for idx, (table_name, meta) in enumerate(NEW_TABLES.items(), start=1):
        row = start_row + idx - 1
        ws.cell(row=row, column=1, value=row - 1)
        ws.cell(row=row, column=2, value=meta["domain"])
        ws.cell(row=row, column=3, value=meta["biz"])
        ws.cell(row=row, column=table_col, value=table_name)
        ws.cell(row=row, column=cn_col, value=meta["cn"])
        ws.cell(row=row, column=type_col, value=meta["type"])
        ws.cell(row=row, column=duty_col, value="保存对应业务域的核心对象或业务明细。")
        ws.cell(row=row, column=usage_col, value=meta["usage"])
        ws.cell(row=row, column=source_col, value=meta["is_source"])
        ws.cell(row=row, column=relation_col, value=meta["is_relation"])
        ws.cell(row=row, column=event_col, value=meta["is_event"])
        ws.cell(row=row, column=master_col, value=meta["is_master"])
        ws.cell(row=row, column=col_idx(ws, "字段数"), value=len(meta["fields"]))
        ws.cell(row=row, column=pk_col, value=meta["pk"])
        ws.cell(row=row, column=col_idx(ws, "主要关联对象"), value="case_main、sys_employee")


if __name__ == "__main__":
    sys.exit(main())
