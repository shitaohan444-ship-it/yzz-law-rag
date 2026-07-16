# -*- coding: utf-8 -*-
"""MinIO 附件业务绑定 - Excel 同步（幂等，可重跑）。

- 06_全字段数据字典：sys_attachment 新增 bucket / object_key / etag
- 10_索引清单：新增 ix_sys_attachment_object_key
"""
from pathlib import Path
from copy import copy
import openpyxl

EXCEL = Path(__file__).resolve().parents[2] / "docs" / "律所综合业务数据库v2.16_最终冻结版.xlsx"

# (字段名, 中文名, 数据类型, 约束, 绑定字典编码, 字典说明, 字段性质, 字段注释)
NEW_FIELDS = {
    "sys_attachment": [
        ("bucket", "存储桶", "VARCHAR(100)", "—", "—", "—", "业务字段",
         "对象存储 bucket 名（如 law-firm-files）；NAS 场景可空。"),
        ("object_key", "对象键", "VARCHAR(500)", "—", "—", "—", "业务字段",
         "对象存储对象键，下载与预签名 URL 的定位依据。"),
        ("etag", "ETag校验值", "VARCHAR(128)", "—", "—", "—", "业务字段",
         "对象存储返回的 etag，用于完整性校验。"),
    ],
}

# (表名, 中文表名, 索引名, 是否唯一, 索引字段, 定义)
NEW_INDEXES = [
    ("sys_attachment", "附件表", "ix_sys_attachment_object_key", "否", "object_key",
     "CREATE INDEX ix_sys_attachment_object_key ON oa.sys_attachment USING btree (object_key)"),
]


def copy_style(src, dst):
    if src.has_style:
        dst.font = copy(src.font)
        dst.fill = copy(src.fill)
        dst.border = copy(src.border)
        dst.alignment = copy(src.alignment)
        dst.number_format = src.number_format


def sync_06(wb):
    ws = wb["06_全字段数据字典"]
    n = 0
    for table, fields in NEW_FIELDS.items():
        rows = [r for r in range(2, ws.max_row + 1) if str(ws.cell(r, 4).value) == table]
        if not rows:
            print(f"  [06] 未找到表 {table}"); continue
        existing = {str(ws.cell(r, 8).value) for r in rows}
        todo = [f for f in fields if f[0] not in existing]
        if not todo:
            print(f"  [06] {table}: 已是最新，跳过"); continue
        last_row, first_row = rows[-1], rows[0]
        max_seq = max((ws.cell(r, 7).value for r in rows if isinstance(ws.cell(r, 7).value, int)), default=0)
        ws.insert_rows(last_row + 1, len(todo))
        for i, (name, cn, dtype, cons, dct, ddesc, nature, note) in enumerate(todo):
            r = last_row + 1 + i
            ws.cell(r, 2).value = ws.cell(first_row, 2).value
            ws.cell(r, 3).value = ws.cell(first_row, 3).value
            ws.cell(r, 4).value = table
            ws.cell(r, 5).value = ws.cell(first_row, 5).value
            ws.cell(r, 6).value = ws.cell(first_row, 6).value
            ws.cell(r, 7).value = max_seq + 1 + i
            ws.cell(r, 8).value = name
            ws.cell(r, 9).value = cn
            ws.cell(r, 10).value = dtype
            ws.cell(r, 11).value = "YES"
            ws.cell(r, 12).value = cons
            ws.cell(r, 13).value = dct
            ws.cell(r, 14).value = ddesc
            ws.cell(r, 15).value = nature
            ws.cell(r, 16).value = ws.cell(first_row, 16).value
            ws.cell(r, 17).value = note
            for c in range(1, 18):
                copy_style(ws.cell(last_row, c), ws.cell(r, c))
            n += 1
        print(f"  [06] {table}: 新增 {len(todo)} 字段")
    return n


def sync_10(wb):
    ws = wb["10_索引清单"]
    existing = {str(ws.cell(r, 4).value) for r in range(2, ws.max_row + 1)}
    template_row = 2
    n = 0
    for tbl, cn, idx_name, unique, fld, ddl in NEW_INDEXES:
        if idx_name in existing:
            print(f"  [10] {idx_name}: 已存在，跳过"); continue
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
    bak = EXCEL.with_name("律所综合业务数据库v2.16_最终冻结版.before_attachment.bak")
    if not bak.exists():
        import shutil
        shutil.copy2(EXCEL, bak)
        print(f"已备份 → {bak.name}")
    else:
        print(f"备份已存在，跳过: {bak.name}")
    wb = openpyxl.load_workbook(EXCEL)
    print("\n--- 06 全字段数据字典 ---"); sync_06(wb)
    print("\n--- 10 索引清单 ---"); sync_10(wb)
    wb.save(EXCEL)
    print(f"\n已保存: {EXCEL}")


if __name__ == "__main__":
    main()
