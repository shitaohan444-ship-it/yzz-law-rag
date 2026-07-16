# -*- coding: utf-8 -*-
"""v2.17 业务字段闭环 - Excel 同步（幂等，可重跑）。

同步内容：
- 06_全字段数据字典：case_material/case_status_log/case_close_review 各加字段行
- 07_字典类型清单：assigned_role 改写字符串码 + 新增 case_result/archive_medium
- 08_字典值展开表：assigned_role 改写 + assistant 新增 + case_result/archive_medium 展开
- 09_外键关系清单：case_material.reviewed_by → sys_employee.id
- 10_索引清单：3 个新索引
"""
from pathlib import Path
from copy import copy
import openpyxl

EXCEL = Path(__file__).resolve().parents[2] / "docs" / "律所综合业务数据库v2.16_最终冻结版.xlsx"


# ---------- 06 表新字段 ----------
# (字段名, 中文名, 数据类型, 约束, 绑定字典编码, 字典说明, 字段性质, 字段注释)
NEW_FIELDS = {
    "case_material": [
        ("reviewed_by", "审核人ID", "BIGINT", "FK → sys_employee.id（员工表）", "—", "—", "外键字段",
         "审核人ID，关联员工表的id字段，用于建立案件材料审核闭环。"),
        ("reviewed_at", "审核时间", "TIMESTAMP WITH TIME ZONE", "—", "—", "—", "业务字段",
         "审核时间，记录案件材料审核的发生时间。"),
        ("review_opinion", "审核意见", "TEXT", "—", "—", "—", "业务字段",
         "审核意见，记录审核人给出的文字结论。"),
        ("supplement_requirement", "补正要求", "TEXT", "—", "—", "—", "业务字段",
         "补正要求，审核退回时记录需补充完善的内容。"),
    ],
    "case_status_log": [
        ("next_step_plan", "下一步计划", "TEXT", "—", "—", "—", "业务字段",
         "下一步工作计划，用于明确案件后续推进方向和待办事项。"),
        ("estimated_complete_at", "预计完成时间", "TIMESTAMP WITH TIME ZONE", "—", "—", "—", "业务字段",
         "预计完成时间，用于进度预警和台账展示。"),
        ("customer_cooperation", "客户配合情况", "TEXT", "—", "—", "—", "业务字段",
         "客户配合情况说明，记录客户提供材料、签字、到场的配合状态。"),
        ("supplement_material_flag", "是否需补充材料", "BOOLEAN", "—", "—", "—", "业务字段",
         "是否需要客户补充材料，用于标记待补材料节点。"),
    ],
    "case_close_review": [
        ("customer_notified", "是否已告知客户", "BOOLEAN", "—", "—", "—", "业务字段",
         "是否已告知客户结案，用于结案告知闭环。"),
        ("case_result", "案件结果", "VARCHAR(50)", "—", "case_result", "案件结果", "业务字段",
         "案件结果，绑定字典「case_result/案件结果」，如胜诉、败诉、调解等。"),
        ("unpaid_amount", "未收款金额", "NUMERIC(16,2)", "—", "—", "—", "业务字段",
         "结案时未收款金额快照，用于财务闭环核对。"),
        ("uninvoiced_amount", "未开票金额", "NUMERIC(16,2)", "—", "—", "—", "业务字段",
         "结案时未开票金额快照，用于财务闭环核对。"),
        ("archive_medium", "归档介质", "VARCHAR(50)", "—", "archive_medium", "归档介质", "业务字段",
         "归档介质，绑定字典「archive_medium/归档介质」，如纸质、电子、混合。"),
    ],
}

# ---------- 07 表 ----------
ASSIGNED_ROLE_ENUM = "main_lawyer=主办律师；co_lawyer=协办律师；case_mgr=案管；trainee=实习律师；assistant=律师助理"
ASSIGNED_ROLE_DESC = "字符串码枚举口径（与数据库实际取值/视图一致）；用于案件分配表，区分主办、协办、案管、实习、律师助理。"
NEW_DICT_TYPES = [
    # (字典类别, 中文名, 枚举值, 说明)
    ("case_result", "案件结果", "win=胜诉；loss=败诉；settle=调解结案；partial=部分胜诉；withdraw=撤诉；other=其他",
     "字符串码枚举口径；用于结案审核记录案件最终结果，便于胜败诉统计。"),
    ("archive_medium", "归档介质", "paper=纸质归档；electronic=电子归档；mixed=纸质+电子",
     "字符串码枚举口径；用于结案归档区分介质类型。"),
]

# ---------- 08 表 ----------
ASSIGNED_ROLE_MAP = {"1": "main_lawyer", "2": "co_lawyer", "3": "case_mgr", "4": "trainee"}
# 08 表追加行: (使用部门, 表名, 中文表名, 字段名, 中文字段名, 字典编码, 字典名称, 枚举值, 枚举显示值, 排序, 是否启用, 字段注释)
NEW_DICT_ITEMS = [
    ("案件管理部；律师部", "case_assignment", "案件分配表", "assigned_role", "分案角色", "assigned_role", "分案角色",
     "assistant", "律师助理", 5, "是", "分案角色新增律师助理，进入正式人员分配。"),
    ("案件管理部", "case_close_review", "结案与归档审核表", "case_result", "案件结果", "case_result", "案件结果",
     "win", "胜诉", 1, "是", "案件结果，绑定字典「case_result/案件结果」。"),
    ("案件管理部", "case_close_review", "结案与归档审核表", "case_result", "案件结果", "case_result", "案件结果",
     "loss", "败诉", 2, "是", "案件结果，绑定字典「case_result/案件结果」。"),
    ("案件管理部", "case_close_review", "结案与归档审核表", "case_result", "案件结果", "case_result", "案件结果",
     "settle", "调解结案", 3, "是", "案件结果，绑定字典「case_result/案件结果」。"),
    ("案件管理部", "case_close_review", "结案与归档审核表", "case_result", "案件结果", "case_result", "案件结果",
     "partial", "部分胜诉", 4, "是", "案件结果，绑定字典「case_result/案件结果」。"),
    ("案件管理部", "case_close_review", "结案与归档审核表", "case_result", "案件结果", "case_result", "案件结果",
     "withdraw", "撤诉", 5, "是", "案件结果，绑定字典「case_result/案件结果」。"),
    ("案件管理部", "case_close_review", "结案与归档审核表", "case_result", "案件结果", "case_result", "案件结果",
     "other", "其他", 6, "是", "案件结果，绑定字典「case_result/案件结果」。"),
    ("案件管理部", "case_close_review", "结案与归档审核表", "archive_medium", "归档介质", "archive_medium", "归档介质",
     "paper", "纸质归档", 1, "是", "归档介质，绑定字典「archive_medium/归档介质」。"),
    ("案件管理部", "case_close_review", "结案与归档审核表", "archive_medium", "归档介质", "archive_medium", "归档介质",
     "electronic", "电子归档", 2, "是", "归档介质，绑定字典「archive_medium/归档介质」。"),
    ("案件管理部", "case_close_review", "结案与归档审核表", "archive_medium", "归档介质", "archive_medium", "归档介质",
     "mixed", "纸质+电子", 3, "是", "归档介质，绑定字典「archive_medium/归档介质」。"),
]

# ---------- 09 表 ----------
NEW_FK = ("案件管理部", "case_material", "案件材料表", "源表", "reviewed_by", "sys_employee.id",
          "外键 fk_case_material_reviewer")

# ---------- 10 表 ----------
# (表名, 中文表名, 索引名, 是否唯一, 索引字段, 定义)
NEW_INDEXES = [
    ("case_material", "案件材料表", "ix_case_material_reviewed_by", "否", "reviewed_by",
     "CREATE INDEX ix_case_material_reviewed_by ON oa.case_material USING btree (reviewed_by)"),
    ("case_close_review", "结案与归档审核表", "ix_case_close_review_case_result", "否", "case_result",
     "CREATE INDEX ix_case_close_review_case_result ON oa.case_close_review USING btree (case_result)"),
    ("case_close_review", "结案与归档审核表", "ix_case_close_review_archive_medium", "否", "archive_medium",
     "CREATE INDEX ix_case_close_review_archive_medium ON oa.case_close_review USING btree (archive_medium)"),
]


def copy_style(src_cell, dst_cell):
    if src_cell.has_style:
        dst_cell.font = copy(src_cell.font)
        dst_cell.fill = copy(src_cell.fill)
        dst_cell.border = copy(src_cell.border)
        dst_cell.alignment = copy(src_cell.alignment)
        dst_cell.number_format = src_cell.number_format


def sync_06(wb):
    ws = wb["06_全字段数据字典"]
    n = 0
    for table, fields in NEW_FIELDS.items():
        rows = [r for r in range(2, ws.max_row + 1) if str(ws.cell(r, 4).value) == table]
        if not rows:
            print(f"  [06] 跳过：未找到表 {table}")
            continue
        existing = {str(ws.cell(r, 8).value) for r in rows}
        todo = [f for f in fields if f[0] not in existing]
        if not todo:
            print(f"  [06] {table}: 已是最新，跳过")
            continue
        last_row = rows[-1]
        first_row = rows[0]
        max_fld_seq = max((ws.cell(r, 7).value for r in rows if isinstance(ws.cell(r, 7).value, int)), default=0)
        ws.insert_rows(last_row + 1, len(todo))
        for i, (name, cn, dtype, cons, dct, ddesc, nature, note) in enumerate(todo):
            r = last_row + 1 + i
            ws.cell(r, 2).value = ws.cell(first_row, 2).value   # 主层级
            ws.cell(r, 3).value = ws.cell(first_row, 3).value   # 业务域
            ws.cell(r, 4).value = table                         # 表名
            ws.cell(r, 5).value = ws.cell(first_row, 5).value   # 中文表名
            ws.cell(r, 6).value = ws.cell(first_row, 6).value   # 表类型
            ws.cell(r, 7).value = max_fld_seq + 1 + i           # 字段序号
            ws.cell(r, 8).value = name
            ws.cell(r, 9).value = cn
            ws.cell(r, 10).value = dtype
            ws.cell(r, 11).value = "YES"
            ws.cell(r, 12).value = cons
            ws.cell(r, 13).value = dct
            ws.cell(r, 14).value = ddesc
            ws.cell(r, 15).value = nature
            ws.cell(r, 16).value = ws.cell(first_row, 16).value  # 使用部门
            ws.cell(r, 17).value = note
            for c in range(1, 18):
                copy_style(ws.cell(last_row, c), ws.cell(r, c))
            n += 1
        print(f"  [06] {table}: 新增 {len(todo)} 字段")
    return n


def sync_07(wb):
    ws = wb["07_字典类型清单"]
    n = 0
    # 改写 assigned_role
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(r, 2).value) == "assigned_role":
            if "main_lawyer" in str(ws.cell(r, 4).value or ""):
                print("  [07] assigned_role: 已是字符串码，跳过改写")
            else:
                ws.cell(r, 4).value = ASSIGNED_ROLE_ENUM
                ws.cell(r, 5).value = ASSIGNED_ROLE_DESC
                n += 1
                print("  [07] assigned_role: 改写为字符串码枚举")
            break
    # 新增字典类别
    existing_cats = {str(ws.cell(r, 2).value) for r in range(2, ws.max_row + 1)}
    max_seq = max((ws.cell(r, 1).value for r in range(2, ws.max_row + 1) if isinstance(ws.cell(r, 1).value, int)), default=0)
    template_row = ws.max_row
    appended = 0
    for cat, cn, enums, desc in NEW_DICT_TYPES:
        if cat in existing_cats:
            print(f"  [07] {cat}: 已存在，跳过")
            continue
        max_seq += 1
        r = ws.max_row + 1
        ws.cell(r, 1).value = max_seq
        ws.cell(r, 2).value = cat
        ws.cell(r, 3).value = cn
        ws.cell(r, 4).value = enums
        ws.cell(r, 5).value = desc
        for c in range(1, 6):
            copy_style(ws.cell(template_row, c), ws.cell(r, c))
        appended += 1
        print(f"  [07] 新增字典类别 {cat}")
    return n + appended


def sync_08(wb):
    ws = wb["08_字典值展开表"]
    n = 0
    # 改写 assigned_role 现有4行的枚举值
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(r, 6).value) == "assigned_role":
            val = str(ws.cell(r, 8).value)
            if val in ASSIGNED_ROLE_MAP:
                ws.cell(r, 8).value = ASSIGNED_ROLE_MAP[val]
                n += 1
    if n:
        print(f"  [08] assigned_role: 改写 {n} 行枚举值为字符串码")
    # 追加新项
    existing = {(str(ws.cell(r, 6).value), str(ws.cell(r, 8).value))
                for r in range(2, ws.max_row + 1)}
    template_row = ws.max_row
    appended = 0
    for item in NEW_DICT_ITEMS:
        key = (item[5], item[7])  # 字典编码, 枚举值
        if key in existing:
            continue
        r = ws.max_row + 1
        for c, val in enumerate(item, 1):
            ws.cell(r, c).value = val
        for c in range(1, 13):
            copy_style(ws.cell(template_row, c), ws.cell(r, c))
        existing.add(key)
        appended += 1
    print(f"  [08] 追加 {appended} 行字典值（assistant/case_result/archive_medium）")
    return n + appended


def sync_09(wb):
    ws = wb["09_外键关系清单"]
    dept, src_tbl, src_cn, src_type, src_fld, tgt, desc = NEW_FK
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(r, 4).value) == src_tbl and str(ws.cell(r, 7).value) == src_fld:
            print("  [09] case_material.reviewed_by 外键行已存在，跳过")
            return 0
    max_seq = max((ws.cell(r, 1).value for r in range(2, ws.max_row + 1) if isinstance(ws.cell(r, 1).value, int)), default=0)
    template_row = ws.max_row
    r = ws.max_row + 1
    ws.cell(r, 1).value = max_seq + 1
    ws.cell(r, 2).value = "业务域层"
    ws.cell(r, 3).value = dept
    ws.cell(r, 4).value = src_tbl
    ws.cell(r, 5).value = src_cn
    ws.cell(r, 6).value = src_type
    ws.cell(r, 7).value = src_fld
    ws.cell(r, 8).value = tgt
    ws.cell(r, 9).value = desc
    for c in range(1, 10):
        copy_style(ws.cell(template_row, c), ws.cell(r, c))
    print("  [09] 新增 case_material.reviewed_by 外键行")
    return 1


def sync_10(wb):
    ws = wb["10_索引清单"]
    existing = {str(ws.cell(r, 4).value) for r in range(2, ws.max_row + 1)}
    template_row = 2
    n = 0
    for tbl, cn, idx_name, unique, fld, ddl in NEW_INDEXES:
        if idx_name in existing:
            print(f"  [10] {idx_name}: 已存在，跳过")
            continue
        r = ws.max_row + 1
        ws.cell(r, 2).value = tbl
        ws.cell(r, 3).value = cn
        ws.cell(r, 4).value = idx_name
        ws.cell(r, 5).value = unique
        ws.cell(r, 6).value = fld
        ws.cell(r, 7).value = ddl
        for c in range(1, 8):
            copy_style(ws.cell(template_row, c), ws.cell(r, c))
        n += 1
        print(f"  [10] 新增索引 {idx_name}")
    return n


def main():
    assert EXCEL.exists(), f"Excel 不存在: {EXCEL}"
    bak = EXCEL.with_name("律所综合业务数据库v2.16_最终冻结版.before_bizfield.bak")
    if not bak.exists():
        import shutil
        shutil.copy2(EXCEL, bak)
        print(f"已备份 → {bak.name}")
    else:
        print(f"备份已存在，跳过: {bak.name}")

    wb = openpyxl.load_workbook(EXCEL)
    print("\n--- 06 全字段数据字典 ---"); sync_06(wb)
    print("\n--- 07 字典类型清单 ---"); sync_07(wb)
    print("\n--- 08 字典值展开表 ---"); sync_08(wb)
    print("\n--- 09 外键关系清单 ---"); sync_09(wb)
    print("\n--- 10 索引清单 ---"); sync_10(wb)

    wb.save(EXCEL)
    print(f"\n已保存: {EXCEL}")


if __name__ == "__main__":
    main()
