"""
诊断 v2.16 Excel 工作簿与校验报告之间的不一致。
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

EXCEL_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "律所综合业务数据库v2.16_最终冻结版.xlsx"


def col_idx(ws, header: str) -> int | None:
    for cell in ws[1]:
        if cell.value == header:
            return cell.column
    return None


def main() -> int:
    if not EXCEL_PATH.exists():
        print(f"Excel 不存在: {EXCEL_PATH}", file=sys.stderr)
        return 1

    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)

    print("=" * 60)
    print("工作簿诊断报告")
    print("=" * 60)

    # 01_概览
    ws = wb["01_概览"]
    print("\n## 01_概览 关键指标")
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=3, values_only=True):
        if row[0] and isinstance(row[0], str) and any(k in row[0] for k in ["源表", "外键", "索引", "字典类别", "字段", "视图"]):
            print(f"  {row[0]}: {row[1]}")

    # 03_全表清单
    ws = wb["03_全表清单"]
    table_col = col_idx(ws, "表名")
    source_col = col_idx(ws, "是否源表")
    source_tables = []
    for row in range(2, ws.max_row + 1):
        is_source = ws.cell(row=row, column=source_col).value
        if is_source == "是":
            source_tables.append(ws.cell(row=row, column=table_col).value)
    print(f"\n## 03_全表清单 源表数量: {len(source_tables)}")
    new_tables = ["case_intake_review", "case_assignment_history", "case_file_handover", "case_close_review"]
    for t in new_tables:
        print(f"  {t}: {'存在' if t in source_tables else '缺失'}")

    # 04_建表顺序
    ws = wb["04_建表顺序"]
    table_col = col_idx(ws, "表名")
    build_order_tables = []
    for row in range(2, ws.max_row + 1):
        val = ws.cell(row=row, column=table_col).value
        if val:
            build_order_tables.append(val)
    print(f"\n## 04_建表顺序 表数量: {len(build_order_tables)}")
    for t in new_tables:
        print(f"  {t}: {'存在' if t in build_order_tables else '缺失'}")

    # 06_全字段数据字典
    ws = wb["06_全字段数据字典"]
    print(f"\n## 06_全字段数据字典 总行数（含表头）: {ws.max_row}")

    # 07_字典类型清单
    ws = wb["07_字典类型清单"]
    code_col = col_idx(ws, "字典类别")
    codes = []
    for row in range(2, ws.max_row + 1):
        val = ws.cell(row=row, column=code_col).value
        if val:
            codes.append(val)
    print(f"\n## 07_字典类型清单 总行数（含表头）: {ws.max_row}, 唯一编码数: {len(set(codes))}")

    # 08_字典值展开表
    ws = wb["08_字典值展开表"]
    print(f"\n## 08_字典值展开表 总行数（含表头）: {ws.max_row}")

    # 09_外键关系清单
    ws = wb["09_外键关系清单"]
    print(f"\n## 09_外键关系清单 总行数（含表头）: {ws.max_row}")

    # 10_索引清单
    ws = wb["10_索引清单"]
    print(f"\n## 10_索引清单 总行数（含表头）: {ws.max_row}")

    # 12_市场部流程字段映射
    ws = wb["12_市场部流程字段映射"]
    print(f"\n## 12_市场部流程字段映射 总行数（含表头）: {ws.max_row}")
    table_col = col_idx(ws, "对应表")
    field_col = col_idx(ws, "对应字段")
    suspicious = []
    for row in range(2, ws.max_row + 1):
        table = ws.cell(row=row, column=table_col).value
        field = ws.cell(row=row, column=field_col).value
        if field and any(f in str(field) for f in ["party_name", "assign_status", "ai_summary", "quote_amount", "case_analysis", "lead_id"]):
            suspicious.append((table, field))
    if suspicious:
        print("  可疑字段（可能不存在）:")
        for table, field in suspicious:
            print(f"    {table}.{field}")

    # 13_案管部流程字段映射
    ws = wb["13_案管部流程字段映射"]
    print(f"\n## 13_案管部流程字段映射 总行数（含表头）: {ws.max_row}")
    table_col = col_idx(ws, "对应表")
    tables_used = set()
    for row in range(2, ws.max_row + 1):
        val = ws.cell(row=row, column=table_col).value
        if val:
            tables_used.add(val)
    for t in new_tables:
        print(f"  {t}: {'已引用' if t in tables_used else '未引用'}")

    # 20_修复问题
    if "20_修复问题" in wb.sheetnames:
        ws = wb["20_修复问题"]
        print(f"\n## 20_修复问题 总行数（含表头）: {ws.max_row}")
    else:
        print("\n## 20_修复问题: 工作表不存在")

    # 数据类型抽样检查
    ws = wb["06_全字段数据字典"]
    type_col = col_idx(ws, "数据类型")
    non_pg_types = set()
    for row in range(2, ws.max_row + 1):
        val = ws.cell(row=row, column=type_col).value
        if val and any(t in str(val).upper() for t in ["BIGINT UNSIGNED", "DATETIME", "TINYINT", "LONGTEXT"]):
            non_pg_types.add(str(val))
    print(f"\n## 非 PostgreSQL 原生类型抽样（前 20）:")
    for t in sorted(non_pg_types)[:20]:
        print(f"  {t}")

    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
