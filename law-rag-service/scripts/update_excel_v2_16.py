"""
修复 v2.16 Excel 设计文件中的已知问题，并回填新增表/字典。

使用前请先备份 Excel。脚本默认输出到新文件，确认无误后再覆盖原文件。
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

EXCEL_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "律所综合业务数据库v2.16_最终冻结版.xlsx"
OUTPUT_PATH = EXCEL_PATH.with_name(EXCEL_PATH.stem + "_fixed.xlsx")

# 新增表定义（字段顺序与模型一致）
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
            ("id", "主键ID", "BIGINT UNSIGNED", "NO", "PK", "—", "收案审核记录主键，自增唯一标识。"),
            ("intake_handover_id", "收案移交ID", "BIGINT UNSIGNED", "NO", "—", "—", "关联收案移交记录ID，用于建立收案审核与移交记录之间的业务关系。"),
            ("case_id", "案件ID", "BIGINT UNSIGNED", "YES", "—", "—", "关联案件主表ID；建案前为空，建案后回填。"),
            ("review_aspect", "审核维度", "VARCHAR(80)", "NO", "—", "intake_review_aspect", "审核维度，绑定字典「intake_review_aspect/收案审核维度」。"),
            ("reviewer_id", "审核人ID", "BIGINT UNSIGNED", "YES", "—", "—", "审核人ID，关联员工表。"),
            ("review_time", "审核时间", "DATETIME", "YES", "—", "—", "审核时间。"),
            ("review_opinion", "审核意见", "TEXT", "YES", "—", "—", "审核意见。"),
            ("review_result", "审核结果", "VARCHAR(50)", "YES", "—", "review_result", "审核结果，绑定字典「review_result/审核结果」。"),
            ("supplement_requirement", "补充要求", "TEXT", "YES", "—", "—", "退回补充时要求补充的材料或说明。"),
            ("previous_review_id", "前次审核ID", "BIGINT UNSIGNED", "YES", "—", "—", "前一次审核记录ID，用于形成补正审核链条。"),
            ("customer_visible", "客户可见标记", "TINYINT(1)", "NO", "—", "customer_visible", "客户可见标记。"),
            ("created_at", "创建时间", "DATETIME", "NO", "—", "—", "记录创建时间。"),
            ("created_by", "创建人ID", "BIGINT UNSIGNED", "YES", "—", "—", "记录创建人ID。"),
            ("updated_at", "更新时间", "DATETIME", "NO", "—", "—", "记录最近更新时间。"),
            ("updated_by", "更新人ID", "BIGINT UNSIGNED", "YES", "—", "—", "记录最后修改人ID。"),
            ("deleted_at", "软删除时间", "DATETIME", "YES", "—", "—", "软删除时间；为空表示有效。"),
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
            ("id", "主键ID", "BIGINT UNSIGNED", "NO", "PK", "—", "案件分配变更历史主键，自增唯一标识。"),
            ("case_assignment_id", "案件分配ID", "BIGINT UNSIGNED", "YES", "—", "—", "关联当前生效的案件分配记录ID。"),
            ("case_id", "案件ID", "BIGINT UNSIGNED", "NO", "—", "—", "关联案件主表ID。"),
            ("assigned_role", "分案角色", "VARCHAR(50)", "NO", "—", "assigned_role", "分案角色，绑定字典「assigned_role/分案角色」。"),
            ("previous_employee_id", "原负责人ID", "BIGINT UNSIGNED", "YES", "—", "—", "原负责人ID。"),
            ("new_employee_id", "新负责人ID", "BIGINT UNSIGNED", "NO", "—", "—", "新负责人ID。"),
            ("change_reason", "变更原因", "VARCHAR(500)", "YES", "—", "—", "变更原因。"),
            ("adjustment_request_id", "调整申请审批ID", "BIGINT UNSIGNED", "YES", "—", "—", "关联调整申请审批记录ID。"),
            ("transfer_material_list_json", "交接材料清单", "JSON", "YES", "—", "—", "交接材料清单，可保存材料类型、附件ID、是否交接等。"),
            ("transfer_completed_at", "交接完成时间", "DATETIME", "YES", "—", "—", "交接完成时间。"),
            ("archive_review_status", "卷宗交接审核状态", "TINYINT", "YES", "—", "archive_review_status", "卷宗交接审核状态，1待审核、2审核通过、3退回补充、4审核不通过。"),
            ("archive_reviewed_by", "卷宗交接审核人ID", "BIGINT UNSIGNED", "YES", "—", "—", "卷宗交接审核人ID。"),
            ("archive_reviewed_at", "卷宗交接审核时间", "DATETIME", "YES", "—", "—", "卷宗交接审核时间。"),
            ("effective_from", "生效时间", "DATETIME", "NO", "—", "—", "该分配生效时间。"),
            ("effective_to", "失效时间", "DATETIME", "YES", "—", "—", "该分配失效时间；为空表示当前生效。"),
            ("is_current", "是否当前生效", "TINYINT(1)", "NO", "—", "yes_no", "是否当前生效记录。"),
            ("created_at", "创建时间", "DATETIME", "NO", "—", "—", "记录创建时间。"),
            ("created_by", "创建人ID", "BIGINT UNSIGNED", "YES", "—", "—", "记录创建人ID。"),
            ("updated_at", "更新时间", "DATETIME", "NO", "—", "—", "记录最近更新时间。"),
            ("updated_by", "更新人ID", "BIGINT UNSIGNED", "YES", "—", "—", "记录最后修改人ID。"),
            ("deleted_at", "软删除时间", "DATETIME", "YES", "—", "—", "软删除时间；为空表示有效。"),
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
            ("id", "主键ID", "BIGINT UNSIGNED", "NO", "PK", "—", "案件内部交接主键，自增唯一标识。"),
            ("case_id", "案件ID", "BIGINT UNSIGNED", "NO", "—", "—", "关联案件主表ID。"),
            ("handover_type", "交接类型", "VARCHAR(80)", "NO", "—", "file_handover_type", "交接类型，绑定字典「file_handover_type/交接类型」。"),
            ("from_employee_id", "移交人ID", "BIGINT UNSIGNED", "NO", "—", "—", "移交人ID。"),
            ("to_employee_id", "接收人ID", "BIGINT UNSIGNED", "NO", "—", "—", "接收人ID。"),
            ("handover_status", "交接状态", "VARCHAR(80)", "NO", "—", "file_handover_status", "交接状态，绑定字典「file_handover_status/交接状态」。"),
            ("material_list_json", "交接材料清单", "JSON", "YES", "—", "—", "交接材料清单。"),
            ("handover_time", "移交时间", "DATETIME", "YES", "—", "—", "移交时间。"),
            ("received_time", "接收时间", "DATETIME", "YES", "—", "—", "接收时间。"),
            ("archive_review_status", "卷宗交接审核状态", "TINYINT", "YES", "—", "archive_review_status", "卷宗交接审核状态，1待审核、2审核通过、3退回补充、4审核不通过。"),
            ("archive_reviewed_by", "卷宗交接审核人ID", "BIGINT UNSIGNED", "YES", "—", "—", "卷宗交接审核人ID。"),
            ("archive_reviewed_at", "卷宗交接审核时间", "DATETIME", "YES", "—", "—", "卷宗交接审核时间。"),
            ("created_at", "创建时间", "DATETIME", "NO", "—", "—", "记录创建时间。"),
            ("created_by", "创建人ID", "BIGINT UNSIGNED", "YES", "—", "—", "记录创建人ID。"),
            ("updated_at", "更新时间", "DATETIME", "NO", "—", "—", "记录最近更新时间。"),
            ("updated_by", "更新人ID", "BIGINT UNSIGNED", "YES", "—", "—", "记录最后修改人ID。"),
            ("deleted_at", "软删除时间", "DATETIME", "YES", "—", "—", "软删除时间；为空表示有效。"),
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
            ("id", "主键ID", "BIGINT UNSIGNED", "NO", "PK", "—", "结案归档审核主键，自增唯一标识。"),
            ("case_id", "案件ID", "BIGINT UNSIGNED", "NO", "—", "—", "关联案件主表ID。"),
            ("review_type", "审核类型", "VARCHAR(80)", "NO", "—", "close_review_type", "审核类型，绑定字典「close_review_type/结案审核类型」。"),
            ("applicant_employee_id", "申请人ID", "BIGINT UNSIGNED", "NO", "—", "—", "申请人ID。"),
            ("reviewer_employee_id", "审核人ID", "BIGINT UNSIGNED", "YES", "—", "—", "审核人ID。"),
            ("review_status", "审核状态", "TINYINT", "NO", "—", "close_review_status", "审核状态，1待审核、2审核通过、3退回补充、4审核不通过。"),
            ("review_opinion", "审核意见", "TEXT", "YES", "—", "—", "审核意见。"),
            ("close_date", "结案日期", "DATE", "YES", "—", "—", "结案日期。"),
            ("archive_date", "归档日期", "DATE", "YES", "—", "—", "归档日期。"),
            ("archive_location", "归档位置", "VARCHAR(500)", "YES", "—", "—", "归档位置（纸质/电子）。"),
            ("material_complete_flag", "材料是否齐全", "TINYINT(1)", "YES", "—", "yes_no", "材料是否齐全。"),
            ("customer_visible", "客户可见标记", "TINYINT(1)", "NO", "—", "customer_visible", "客户可见标记。"),
            ("created_at", "创建时间", "DATETIME", "NO", "—", "—", "记录创建时间。"),
            ("created_by", "创建人ID", "BIGINT UNSIGNED", "YES", "—", "—", "记录创建人ID。"),
            ("updated_at", "更新时间", "DATETIME", "NO", "—", "—", "记录最近更新时间。"),
            ("updated_by", "更新人ID", "BIGINT UNSIGNED", "YES", "—", "—", "记录最后修改人ID。"),
            ("deleted_at", "软删除时间", "DATETIME", "YES", "—", "—", "软删除时间；为空表示有效。"),
            ("status", "通用状态", "VARCHAR(32)", "NO", "—", "status", "通用记录状态。"),
            ("remark", "备注", "VARCHAR(500)", "YES", "—", "—", "备注字段。"),
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

# 流程映射字段修正
MAPPING_REPLACEMENTS = {
    "assigned_employee_id": "employee_id",
    "call_time": "call_start_time",
    "duration_seconds": "call_duration_seconds",
    "deal_amount": "agreement_amount",
    "agreement_id": "fee_agreement_id",
    "handover_remark": "remark",
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
        ws.cell(row=agreement_amount_row, column=type_col, value="DECIMAL(16,2)")
        ws.cell(row=agreement_amount_row, column=null_col, value="NO")
        ws.cell(row=agreement_amount_row, column=bind_col, value="—")
        ws.cell(row=agreement_amount_row, column=cn_col, value="协议金额")
        ws.cell(row=agreement_amount_row, column=comment_col,
                value="记录收费协议最终确认的协议金额，用于合同收费、转化金额和后续财务统计。")

    # 在 contract_no 后插入 fee_type 行
    if insert_after_row:
        # 先检查是否已存在 fee_type
        for row in rows:
            if ws.cell(row=row, column=field_col).value == "fee_type":
                return
        new_row = insert_after_row + 1
        ws.insert_rows(new_row)
        # 复制上一行的样式和部分单元格
        prev = new_row - 1
        ws.cell(row=new_row, column=1, value=ws.cell(row=prev, column=1).value + 1)  # 序号递增
        ws.cell(row=new_row, column=2, value=ws.cell(row=prev, column=2).value)  # 主层级
        ws.cell(row=new_row, column=3, value=ws.cell(row=prev, column=3).value)  # 业务域
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


def update_dict_08(ws):
    """更新 08_字典值展开表。"""
    code_col = col_idx(ws, "字典编码")
    name_col = col_idx(ws, "字典名称")
    val_col = col_idx(ws, "枚举值")
    label_col = col_idx(ws, "枚举显示值")
    sort_col = col_idx(ws, "排序")
    enable_col = col_idx(ws, "是否启用")

    # 收集已有键
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

    # 扩展已有字典
    add_items("agreement_status", DICT_UPDATES["agreement_status"], dept="市场部；财务部", table="fin_fee_agreement", field="agreement_status")
    add_items("case_status", DICT_UPDATES["case_status"], dept="案件管理部", table="case_main", field="case_status")

    # 新增字典
    add_items("intake_review_aspect", NEW_DICTS["intake_review_aspect"], dept="案件管理部", table="case_intake_review", field="review_aspect")
    add_items("review_result", NEW_DICTS["review_result"], dept="案件管理部", table="case_intake_review", field="review_result")
    add_items("file_handover_type", NEW_DICTS["file_handover_type"], dept="案件管理部", table="case_file_handover", field="handover_type")
    add_items("file_handover_status", NEW_DICTS["file_handover_status"], dept="案件管理部", table="case_file_handover", field="handover_status")
    add_items("close_review_type", NEW_DICTS["close_review_type"], dept="案件管理部", table="case_close_review", field="review_type")
    add_items("close_review_status", NEW_DICTS["close_review_status"], dept="案件管理部", table="case_close_review", field="review_status")


def add_new_tables_to_full_dict(ws):
    """在 06_全字段数据字典 中追加 4 张新表。"""
    table_col = col_idx(ws, "表名")
    field_col = col_idx(ws, "字段名")
    seq_col = col_idx(ws, "字段序号")

    # 获取当前最大序号
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
    """在 03_全表清单 中追加新表。"""
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


def fix_mapping_sheets(wb):
    """修正流程映射页中的旧字段名。"""
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
            # 特殊处理 payment_plan_id（case_intake_handover 中不存在）
            if "case_intake_handover" in str(ws.cell(row=row, column=col_idx(ws, "对应表")).value or ""):
                new_val = new_val.replace("、payment_plan_id", "").replace("payment_plan_id、", "").replace("payment_plan_id", "")
            ws.cell(row=row, column=field_col, value=new_val)


def main() -> int:
    if not EXCEL_PATH.exists():
        print(f"Excel 文件不存在: {EXCEL_PATH}", file=sys.stderr)
        return 1

    wb = openpyxl.load_workbook(EXCEL_PATH)

    # 1. 修正 06_全字段数据字典
    ws_full = wb["06_全字段数据字典"]
    fix_fin_fee_agreement(ws_full)
    fix_nullable(ws_full, "fin_fee_agreement", "case_id")
    fix_nullable(ws_full, "fin_payment_plan", "case_id")
    add_new_tables_to_full_dict(ws_full)

    # 2. 更新 03_全表清单
    ws_tables = wb["03_全表清单"]
    add_new_tables_to_table_list(ws_tables)

    # 3. 更新字典
    ws_07 = wb["07_字典类型清单"]
    update_dict_07(ws_07)
    ws_08 = wb["08_字典值展开表"]
    update_dict_08(ws_08)

    # 4. 修正流程映射
    fix_mapping_sheets(wb)

    # 保存到新文件
    wb.save(OUTPUT_PATH)
    print(f"已生成修复后的 Excel: {OUTPUT_PATH}")
    print("请人工检查确认后，再覆盖原文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
