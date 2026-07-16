# -*- coding: utf-8 -*-
"""
v2.16 文档层修复脚本（不动数据库）
问题1: 案管流程 fee_fee_agreement_id -> fee_agreement_id
问题2: 07_字典类型清单 补录19个缺失字典
问题3: agreement_amount 约束列清除错误的 fee_type 绑定说明
问题4: 06_全字段数据字典 为4张新增表补录17个外键约束标注
"""
import openpyxl
from copy import copy

PATH = "docs/律所综合业务数据库v2.16_最终冻结版.xlsx"
wb = openpyxl.load_workbook(PATH)  # 不带 data_only，保留格式/公式

changes = []

# ============================================================
# 问题1: 13_案管部流程字段映射 R9 第6列对应字段
# ============================================================
ws13 = wb["13_案管部流程字段映射"]
old1 = ws13.cell(9, 6).value
new1 = old1.replace("fee_fee_agreement_id", "fee_agreement_id")
ws13.cell(9, 6).value = new1
changes.append(("问题1", "13_案管部流程字段映射", "R9C6",
                old1, new1))

# ============================================================
# 问题2: 07_字典类型清单 追加19个字典
# ============================================================
ws7 = wb["07_字典类型清单"]
ws8 = wb["08_字典值展开表"]

missing = ["account_status", "ai_generated_flag", "appointment_created", "code_type",
           "customer_visible", "data_scope", "do_not_disturb", "employment_status",
           "enforcement_level", "gender", "is_primary", "is_system_tag",
           "manual_takeover_flag", "need_follow_up", "nullable_flag", "relation_type",
           "risk_flag", "status", "valid_flag"]

# 从08表实时提取(去重保持顺序)
def extract(code):
    name, enums = None, []
    seen = set()
    for r in range(2, ws8.max_row + 1):
        if str(ws8.cell(r, 6).value or "") == code:
            if name is None:
                name = ws8.cell(r, 7).value
            key = f"{ws8.cell(r, 8).value}={ws8.cell(r, 9).value}"
            if key not in seen:
                seen.add(key)
                enums.append(key)
    return name, "；".join(enums)

# 判断是否布尔标志位(枚举仅含0/1)
def is_flag(enums_str):
    parts = [p.split("=")[0].strip() for p in enums_str.split("；")]
    return sorted(set(parts)) in [["0", "1"], ["1", "0"]]

start_row = ws7.max_row + 1  # 127
template_row = ws7.max_row   # 126 复制样式
seq = 126
for i, code in enumerate(missing):
    r = start_row + i
    name, enums = extract(code)
    desc = "布尔标志位（0=否/1=是）；数字枚举口径" if is_flag(enums) else "数字枚举口径；页面显示中文值"
    ws7.cell(r, 1).value = seq
    ws7.cell(r, 2).value = code
    ws7.cell(r, 3).value = name
    ws7.cell(r, 4).value = enums
    ws7.cell(r, 5).value = desc
    # 复制模板行样式
    for c in range(1, 6):
        src = ws7.cell(template_row, c)
        dst = ws7.cell(r, c)
        if src.has_style:
            dst.font = copy(src.font)
            dst.fill = copy(src.fill)
            dst.border = copy(src.border)
            dst.alignment = copy(src.alignment)
            dst.number_format = src.number_format
    changes.append(("问题2", "07_字典类型清单", f"R{r}",
                    "(空)", f"{seq}/{code}/{name}"))
    seq += 1

# ============================================================
# 问题3: 06_全字段数据字典 fin_fee_agreement.agreement_amount 约束列(第12列)
# ============================================================
ws6 = wb["06_全字段数据字典"]
fixed3 = False
for r in range(2, ws6.max_row + 1):
    if str(ws6.cell(r, 4).value or "") == "fin_fee_agreement" \
       and str(ws6.cell(r, 8).value or "") == "agreement_amount":
        old3 = ws6.cell(r, 12).value
        new3 = "金额（≥0）；收费方式由同表 fee_type 字段独立记录，本字段不绑定字典"
        ws6.cell(r, 12).value = new3
        changes.append(("问题3", "06_全字段数据字典", f"R{r}C12",
                        old3, new3))
        fixed3 = True
        break
assert fixed3, "未找到 agreement_amount 行"

# ============================================================
# 问题4: 06表 为4张新增表补录外键约束(第12列)
#   从09外键清单读取 来源字段->目标表字段，从06表读取 目标表->中文表名
# ============================================================
ws9 = wb["09_外键关系清单"]

# 目标表 -> 中文表名 (从06表第4/5列)
tbl_cn = {}
for r in range(2, ws6.max_row + 1):
    t = ws6.cell(r, 4).value
    cn = ws6.cell(r, 5).value
    if t and t not in tbl_cn:
        tbl_cn[str(t)] = cn

# 外键映射: (来源表, 来源字段) -> 目标表字段
fk_map = {}
for r in range(2, ws9.max_row + 1):
    src_tbl = str(ws9.cell(r, 4).value or "")
    src_fld = str(ws9.cell(r, 7).value or "")
    tgt = str(ws9.cell(r, 8).value or "")  # 形如 case_main.id
    if src_tbl and src_fld and tgt:
        fk_map[(src_tbl, src_fld)] = tgt

new_tables = ["case_intake_review", "case_assignment_history",
              "case_file_handover", "case_close_review"]
fk_count = 0
for r in range(2, ws6.max_row + 1):
    tbl = str(ws6.cell(r, 4).value or "")
    fld = str(ws6.cell(r, 8).value or "")
    if tbl in new_tables and (tbl, fld) in fk_map:
        tgt = fk_map[(tbl, fld)]
        tgt_tbl = tgt.split(".")[0]
        cn = tbl_cn.get(tgt_tbl, "")
        old4 = ws6.cell(r, 12).value
        new4 = f"FK → {tgt}（{cn}）" if cn else f"FK → {tgt}"
        ws6.cell(r, 12).value = new4
        changes.append(("问题4", "06_全字段数据字典", f"R{r}C12 [{tbl}.{fld}]",
                        old4, new4))
        fk_count += 1

# ============================================================
# 保存前打印所有改动
# ============================================================
print(f"共 {len(changes)} 处改动（其中外键补录 {fk_count} 个）:")
for tag, sheet, cell, old, new in changes:
    o = str(old)[:40]
    n = str(new)[:60]
    print(f"  [{tag}] {sheet} {cell}")
    print(f"        旧: {o}")
    print(f"        新: {n}")

wb.save(PATH)
print(f"\n已保存: {PATH}")
print(f"07_字典类型清单 现总行数: {ws7.max_row} (新增 {len(missing)} 行)")
