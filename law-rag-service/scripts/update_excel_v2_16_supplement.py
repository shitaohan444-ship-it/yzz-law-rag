"""
补充更新 v2.16 Excel 的 05_字段字典、09_外键关系清单、10_索引清单。
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

EXCEL_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "律所综合业务数据库v2.16_最终冻结版.xlsx"
OUTPUT_PATH = EXCEL_PATH.with_name(EXCEL_PATH.stem + "_supp.xlsx")

# 05_字段字典：新增字典绑定字段（含 fee_type 修正）
FIELD_DICT_ROWS = [
    # 修正/补充 fin_fee_agreement
    ("业务域层", "财务合同域", "fin_fee_agreement", "收费协议表", "fee_type", "收费方式", "VARCHAR(80)", "fee_type", "收费方式", "市场部；财务部", "记录收费方式，绑定字典「fee_type/收费方式」。"),
    ("业务域层", "财务合同域", "fin_fee_agreement", "收费协议表", "agreement_status", "协议状态", "VARCHAR(50)", "agreement_status", "协议状态", "市场部；财务部", "记录协议状态，绑定字典「agreement_status/协议状态」。"),
    # 新表字典绑定字段
    ("业务域层", "案件管理域", "case_intake_review", "收案审核记录表", "review_aspect", "审核维度", "VARCHAR(80)", "intake_review_aspect", "收案审核维度", "案件管理部", "审核维度，绑定字典「intake_review_aspect/收案审核维度」。"),
    ("业务域层", "案件管理域", "case_intake_review", "收案审核记录表", "review_result", "审核结果", "VARCHAR(50)", "review_result", "审核结果", "案件管理部", "审核结果，绑定字典「review_result/审核结果」。"),
    ("业务域层", "案件管理域", "case_assignment_history", "案件分配变更历史表", "assigned_role", "分案角色", "VARCHAR(50)", "assigned_role", "分案角色", "案件管理部；律师部", "分案角色，绑定字典「assigned_role/分案角色」。"),
    ("业务域层", "案件管理域", "case_assignment_history", "案件分配变更历史表", "archive_review_status", "卷宗交接审核状态", "TINYINT", "archive_review_status", "卷宗审核状态", "案件管理部", "卷宗交接审核状态，1待审核、2审核通过、3退回补充、4审核不通过。"),
    ("业务域层", "案件管理域", "case_file_handover", "案件内部卷宗/人员交接表", "handover_type", "交接类型", "VARCHAR(80)", "file_handover_type", "交接类型", "案件管理部；律师部", "交接类型，绑定字典「file_handover_type/交接类型」。"),
    ("业务域层", "案件管理域", "case_file_handover", "案件内部卷宗/人员交接表", "handover_status", "交接状态", "VARCHAR(80)", "file_handover_status", "交接状态", "案件管理部；律师部", "交接状态，绑定字典「file_handover_status/交接状态」。"),
    ("业务域层", "案件管理域", "case_file_handover", "案件内部卷宗/人员交接表", "archive_review_status", "卷宗交接审核状态", "TINYINT", "archive_review_status", "卷宗审核状态", "案件管理部", "卷宗交接审核状态，1待审核、2审核通过、3退回补充、4审核不通过。"),
    ("业务域层", "案件管理域", "case_close_review", "结案与归档审核表", "review_type", "审核类型", "VARCHAR(80)", "close_review_type", "结案审核类型", "案件管理部", "审核类型，绑定字典「close_review_type/结案审核类型」。"),
    ("业务域层", "案件管理域", "case_close_review", "结案与归档审核表", "review_status", "审核状态", "TINYINT", "close_review_status", "结案审核状态", "案件管理部", "审核状态，1待审核、2审核通过、3退回补充、4审核不通过。"),
]

# 09_外键关系清单：新增外键
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

# 10_索引清单：新增索引
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


def col_idx(ws, header: str) -> int:
    for cell in ws[1]:
        if cell.value == header:
            return cell.column
    raise ValueError(f"表头未找到: {header}")


def update_sheet_05(ws):
    table_col = col_idx(ws, "表名")
    field_col = col_idx(ws, "字段名")
    # 删除 fin_fee_agreement.agreement_amount 的错误字典绑定（如果存在）
    for row in range(2, ws.max_row + 1):
        if ws.cell(row=row, column=table_col).value == "fin_fee_agreement" and ws.cell(row=row, column=field_col).value == "agreement_amount":
            ws.cell(row=row, column=col_idx(ws, "绑定字典编码"), value="—")
            ws.cell(row=row, column=col_idx(ws, "字典名称"), value="—")

    start_row = ws.max_row + 1
    for idx, (layer, biz, table, cn, field, fcn, dtype, bind, dict_name, usage, comment) in enumerate(FIELD_DICT_ROWS, start=1):
        row = start_row + idx - 1
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


def update_sheet_09(ws):
    start_row = ws.max_row + 1
    for idx, (layer, usage, src_table, src_cn, src_type, src_field, target, note) in enumerate(FK_ROWS, start=1):
        row = start_row + idx - 1
        ws.cell(row=row, column=1, value=row - 1)
        ws.cell(row=row, column=col_idx(ws, "主层级"), value=layer)
        ws.cell(row=row, column=col_idx(ws, "使用部门"), value=usage)
        ws.cell(row=row, column=col_idx(ws, "来源表"), value=src_table)
        ws.cell(row=row, column=col_idx(ws, "来源表中文"), value=src_cn)
        ws.cell(row=row, column=col_idx(ws, "来源表类型"), value=src_type)
        ws.cell(row=row, column=col_idx(ws, "来源字段"), value=src_field)
        ws.cell(row=row, column=col_idx(ws, "目标表字段"), value=target)
        ws.cell(row=row, column=col_idx(ws, "说明"), value=note)


def update_sheet_10(ws):
    start_row = ws.max_row + 1
    for idx, (table, cn, idx_name, unique, fields, definition) in enumerate(INDEX_ROWS, start=1):
        row = start_row + idx - 1
        ws.cell(row=row, column=1, value=row - 1)
        ws.cell(row=row, column=col_idx(ws, "表名"), value=table)
        ws.cell(row=row, column=col_idx(ws, "中文表名"), value=cn)
        ws.cell(row=row, column=col_idx(ws, "索引名"), value=idx_name)
        ws.cell(row=row, column=col_idx(ws, "是否唯一"), value=unique)
        ws.cell(row=row, column=col_idx(ws, "索引字段"), value=fields)
        ws.cell(row=row, column=col_idx(ws, "定义"), value=definition)


def main() -> int:
    if not EXCEL_PATH.exists():
        print(f"Excel 不存在: {EXCEL_PATH}", file=sys.stderr)
        return 1

    wb = openpyxl.load_workbook(EXCEL_PATH)
    update_sheet_05(wb["05_字段字典"])
    update_sheet_09(wb["09_外键关系清单"])
    update_sheet_10(wb["10_索引清单"])
    wb.save(OUTPUT_PATH)
    print(f"已生成补充更新后的 Excel: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
