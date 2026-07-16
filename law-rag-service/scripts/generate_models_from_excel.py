"""
读取律所 OA 数据库设计 Excel，自动生成 SQLAlchemy 2.0 Declarative 模型。

Usage:
    .venv\Scripts\python.exe scripts\generate_models_from_excel.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
EXCEL_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "律所综合业务数据库v2.16_最终冻结版.xlsx"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "app" / "models"
VIEW_METADATA_PATH = Path(__file__).resolve().parent / "view_metadata.json"

# 当前批次：第 1-10 阶段表
PHASE_1_10_TABLES = [
    # 第1阶段：系统基础、字典、权限、附件与NAS
    "sys_dict_type",
    "sys_dict_item",
    "sys_dict_item_relation",
    "sys_dict_field_binding",
    "sys_department",
    "sys_employee",
    "sys_user",
    "sys_role",
    "sys_user_role",
    "sys_code_sequence",
    "sys_storage_repository",
    "nas_folder_rule",
    "sys_attachment",
    "sys_attachment_relation",
    "sys_tag",
    "sys_tag_relation",
    "sys_approval_record",
    "sys_notification",
    "sys_operation_log",
    "sys_data_export_log",
    # 第2阶段：客户、当事人与联系人主数据
    "party_main",
    "crm_client",
    "crm_contact",
    "client_party_relation",
    # 第3阶段：运营获客、投放与来源归因
    "ops_content_asset",
    "ops_ad_campaign",
    "ops_ad_creative",
    "ops_ad_spend_daily",
    "ops_live_session",
    "ops_live_lead",
    "lead_source_touch",
    # 第4阶段：市场线索、电邀、线下拓展、预约与谈案
    "crm_lead",
    "lead_party_relation",
    "lead_assignment_log",
    "crm_follow_up",
    "crm_consultation",
    "case_conflict_check",
    "mkt_call_task",
    "mkt_call_task_item",
    "mkt_call_record",
    "mkt_call_quality_review",
    "mkt_appointment",
    "mkt_appointment_change_log",
    "lead_negotiation_record",
    "mkt_employee_kpi_target",
    "mkt_employee_kpi_result",
    # 第5阶段：市场签约、回款计划与案管移交
    "fin_fee_agreement",
    "fin_payment_plan",
    "case_intake_handover",
    # 第6阶段：案管收案建档、分配与调档
    "case_main",
    "case_party",
    "case_assignment",
    "case_assignment_history",
    "case_file_handover",
    "case_material",
    "case_retrieval_task",
    "case_retrieval_task_log",
    "case_status_log",
    "case_intake_review",
    "case_close_review",
    # 第7阶段：律师办案、文书、期限与庭审
    "legal_work_log",
    "legal_document",
    "legal_deadline",
    "court_hearing",
    "court_hearing_attendee",
    "evidence_item",
    # 第8阶段：财务回款、开票、退费与异常跟进
    "fin_payment_followup",
    "fin_payment_record",
    "fin_invoice",
    "fin_refund_record",
    # 第9阶段：管理行政与绩效
    "admin_contract",
    "admin_asset",
    "admin_performance_kpi",
    # 第10阶段：知识库与AI分析支撑
    "kb_document",
    "ai_chat_log",
    "ai_transcription_record",
    "ai_analysis_record",
    "ai_analysis_review",
    # 第11阶段之前的统计分析源表
    "stat_metric_definition",
    "stat_mkt_employee_monthly_snapshot",
]

# 第11阶段：统计视图
PHASE_11_VIEWS = [
    "v_ops_live_effect",
    "v_ops_channel_daily_report",
    "v_lead_conversion_funnel",
    "v_mkt_call_invitation_ledger",
    "v_mkt_visit_negotiation_ledger",
    "v_mkt_employee_performance",
    "v_case_management_ledger",
    "v_case_progress_dashboard",
    "v_payment_collection_summary",
]

VIEWS_FILE = "oa_views"

# 业务域 -> 模型文件映射
DOMAIN_FILES: dict[str, str] = {
    "sys_dict_type": "oa_system",
    "sys_dict_item": "oa_system",
    "sys_dict_item_relation": "oa_system",
    "sys_dict_field_binding": "oa_system",
    "sys_department": "oa_system",
    "sys_employee": "oa_system",
    "sys_user": "oa_system",
    "sys_role": "oa_system",
    "sys_user_role": "oa_system",
    "sys_code_sequence": "oa_system",
    "sys_storage_repository": "oa_system",
    "nas_folder_rule": "oa_system",
    "sys_attachment": "oa_system",
    "sys_attachment_relation": "oa_system",
    "sys_tag": "oa_system",
    "sys_tag_relation": "oa_system",
    "sys_approval_record": "oa_system",
    "sys_notification": "oa_system",
    "sys_operation_log": "oa_system",
    "sys_data_export_log": "oa_system",
    "party_main": "oa_party_client",
    "crm_client": "oa_party_client",
    "crm_contact": "oa_party_client",
    "client_party_relation": "oa_party_client",
    "ops_content_asset": "oa_operation",
    "ops_ad_campaign": "oa_operation",
    "ops_ad_creative": "oa_operation",
    "ops_ad_spend_daily": "oa_operation",
    "ops_live_session": "oa_operation",
    "ops_live_lead": "oa_operation",
    "lead_source_touch": "oa_operation",
    "crm_lead": "oa_marketing",
    "lead_party_relation": "oa_marketing",
    "lead_assignment_log": "oa_marketing",
    "crm_follow_up": "oa_marketing",
    "crm_consultation": "oa_marketing",
    "case_conflict_check": "oa_marketing",
    "mkt_call_task": "oa_marketing",
    "mkt_call_task_item": "oa_marketing",
    "mkt_call_record": "oa_marketing",
    "mkt_call_quality_review": "oa_marketing",
    "mkt_appointment": "oa_marketing",
    "mkt_appointment_change_log": "oa_marketing",
    "lead_negotiation_record": "oa_marketing",
    "mkt_employee_kpi_target": "oa_marketing",
    "mkt_employee_kpi_result": "oa_marketing",
    "fin_fee_agreement": "oa_finance_contract",
    "fin_payment_plan": "oa_finance_contract",
    "case_intake_handover": "oa_case",
    "case_main": "oa_case",
    "case_party": "oa_case",
    "case_assignment": "oa_case",
    "case_assignment_history": "oa_case",
    "case_file_handover": "oa_case",
    "case_material": "oa_case",
    "case_retrieval_task": "oa_case",
    "case_retrieval_task_log": "oa_case",
    "case_status_log": "oa_case",
    "case_intake_review": "oa_case",
    "case_close_review": "oa_case",
    "legal_work_log": "oa_legal",
    "legal_document": "oa_legal",
    "legal_deadline": "oa_legal",
    "court_hearing": "oa_legal",
    "court_hearing_attendee": "oa_legal",
    "evidence_item": "oa_legal",
    "fin_payment_followup": "oa_finance",
    "fin_payment_record": "oa_finance",
    "fin_invoice": "oa_finance",
    "fin_refund_record": "oa_finance",
    "admin_contract": "oa_admin",
    "admin_asset": "oa_admin",
    "admin_performance_kpi": "oa_admin",
    "kb_document": "oa_knowledge_ai",
    "ai_chat_log": "oa_knowledge_ai",
    "ai_transcription_record": "oa_knowledge_ai",
    "ai_analysis_record": "oa_knowledge_ai",
    "ai_analysis_review": "oa_knowledge_ai",
    "stat_metric_definition": "oa_stat",
    "stat_mkt_employee_monthly_snapshot": "oa_stat",
}

# ---------------------------------------------------------------------------
# 类型映射
# ---------------------------------------------------------------------------
def map_column_type(data_type: str) -> tuple[str, dict[str, Any]]:
    """把 Excel 中的数据类型映射为 SQLAlchemy 构造参数。"""
    data_type = data_type.strip().upper()

    # BIGINT UNSIGNED / BIGINT
    if data_type.startswith("BIGINT"):
        return "BigInteger", {}

    # INT / INTEGER / SMALLINT
    if data_type in ("INT", "INTEGER", "SMALLINT"):
        return "SmallInteger" if data_type == "SMALLINT" else "Integer", {}

    # TINYINT
    if data_type.startswith("TINYINT"):
        if "(1)" in data_type:
            return "Boolean", {}
        return "SmallInteger", {}

    # BOOLEAN
    if data_type == "BOOLEAN":
        return "Boolean", {}

    # VARCHAR(N)
    m = re.match(r"VARCHAR\((\d+)\)", data_type)
    if m:
        return "String", {"length": int(m.group(1))}

    # CHAR(N)
    m = re.match(r"CHAR\((\d+)\)", data_type)
    if m:
        return "String", {"length": int(m.group(1))}

    # TEXT / LONGTEXT
    if data_type in ("TEXT", "LONGTEXT"):
        return "Text", {}

    # DATETIME / TIMESTAMP / TIMESTAMP WITH TIME ZONE
    if data_type.startswith("TIMESTAMP") or data_type == "DATETIME":
        return "DateTime", {"timezone": True}

    # DATE
    if data_type == "DATE":
        return "Date", {}

    # DECIMAL(P,S) / NUMERIC(P,S)
    m = re.match(r"(DECIMAL|NUMERIC)\((\d+),\s*(\d+)\)", data_type)
    if m:
        return "Numeric", {"precision": int(m.group(2)), "scale": int(m.group(3))}

    # JSON / JSONB
    if data_type in ("JSON", "JSONB"):
        return "JSON", {}

    raise ValueError(f"未知数据类型: {data_type}")


def parse_nullable_default(null_default: str) -> tuple[bool | None, str | None]:
    """解析 '空值/默认' 列。"""
    lines = [line.strip() for line in null_default.split("\n") if line.strip()]
    nullable = None
    default = None
    for line in lines:
        if line == "必填":
            nullable = False
        elif line == "可空":
            nullable = True
        elif line.startswith("默认："):
            default = line.replace("默认：", "").strip()
            if default == "—":
                default = None
    return nullable, default


def parse_constraints(constraint_text: str) -> dict[str, Any]:
    """解析 '主键/外键/约束' 列。"""
    text = str(constraint_text).strip()
    result: dict[str, Any] = {"pk": False, "fks": [], "uks": []}
    if text == "—" or text.lower() == "nan":
        return result

    # 主键
    if "PK" in text:
        result["pk"] = True

    # 外键
    fk_pattern = re.compile(r"FK\s*→\s*([\w.]+)\s*（[^）]*）")
    for match in fk_pattern.finditer(text):
        ref = match.group(1).strip()
        if "." in ref:
            ref_table, ref_col = ref.split(".", 1)
        else:
            ref_table, ref_col = ref, "id"
        result["fks"].append({"ref_table": ref_table, "ref_col": ref_col})

    # 唯一约束
    uk_pattern = re.compile(r"唯一：([^；。\n]+)")
    for match in uk_pattern.finditer(text):
        names = [n.strip() for n in match.group(1).split("/") if n.strip()]
        result["uks"].extend(names)

    return result


def normalize_default(default: str | None, sa_type: str) -> str | None:
    """把 Excel 默认值转换为 Python/SQLAlchemy 可接受的默认值字符串。"""
    if default is None:
        return None

    default = default.strip()
    if default in ("—", "", "NULL"):
        return None

    if default.upper() == "CURRENT_TIMESTAMP":
        return "sa.func.now()"

    if default.upper() == "AUTO_INCREMENT":
        return None  # 主键自增由 Identity 处理

    # 字符串默认值，保留引号
    if default.startswith("'") and default.endswith("'"):
        return repr(default[1:-1])

    # 数字
    if re.match(r"^-?\d+(\.\d+)?$", default):
        return default

    # 布尔/01
    if sa_type == "Boolean":
        if default in ("1", "True", "true"):
            return "True"
        if default in ("0", "False", "false"):
            return "False"

    # 其他字符串
    return repr(default)


# ---------------------------------------------------------------------------
# 代码生成
# ---------------------------------------------------------------------------
def generate_model_code(table_name: str, fields_df: pd.DataFrame) -> str:
    """为单张表生成 SQLAlchemy 模型代码。"""
    class_name = "".join([part.capitalize() for part in table_name.split("_")])

    lines: list[str] = []
    lines.append(f"class {class_name}(Base, AuditMixin, SoftDeleteMixin):")
    lines.append(f'    """{fields_df["中文表名"].iloc[0]}"""')
    lines.append(f'    __tablename__ = "{table_name}"')
    lines.append("")

    # 收集唯一约束（按约束名分组）
    unique_constraints: dict[str, list[str]] = {}

    for _, row in fields_df.iterrows():
        field_name = str(row["字段名"]).strip()
        cn_name = str(row["中文字段名"]).strip()
        data_type = str(row["数据类型"]).strip()
        null_default = str(row["空值/默认"])
        constraint_text = str(row["主键/外键/约束"])
        comment = str(row["字段注释"]).strip() if pd.notna(row["字段注释"]) else ""

        sa_type, type_kwargs = map_column_type(data_type)
        nullable, default = parse_nullable_default(null_default)
        constraints = parse_constraints(constraint_text)

        # 自增主键：BIGINT 类型 + 主键 + AUTO_INCREMENT
        is_auto_pk = (
            constraints["pk"]
            and sa_type == "BigInteger"
            and "AUTO_INCREMENT" in str(row.get("空值/默认", "")).upper()
        )
        if is_auto_pk:
            type_kwargs["identity"] = True

        # 外键：暂不写入模型 ForeignKey，避免循环依赖；后续由独立 migration 添加
        # 唯一约束收集
        for uk_name in constraints["uks"]:
            unique_constraints.setdefault(uk_name, []).append(field_name)

        # default
        norm_default = normalize_default(default, sa_type)
        # Boolean 字段的默认值 1/0 转成 True/False
        if sa_type == "Boolean" and norm_default in ("1", "0"):
            norm_default = "True" if norm_default == "1" else "False"

        # 构造 mapped_column 调用
        kwargs_parts: list[str] = []
        if nullable is not None:
            kwargs_parts.append(f"nullable={nullable}")
        if norm_default is not None:
            kwargs_parts.append(f"default={norm_default}")
        if comment:
            kwargs_parts.append(f"comment={repr(comment)}")

        if constraints["pk"]:
            kwargs_parts.append("primary_key=True")

        kwargs_str = ", ".join(kwargs_parts)

        # 构造 type 调用，identity 放在 type 内部，避免 type_kwargs 与 kwargs 重复 length
        type_extra = dict(type_kwargs)
        identity_arg = ""
        if "identity" in type_extra:
            type_extra.pop("identity")
            identity_arg = "sa.Identity()"

        type_args = ", ".join(
            [identity_arg]
            + [
                f"{k}={repr(v) if isinstance(v, str) else v}"
                for k, v in type_extra.items()
            ]
        )
        type_args = type_args.strip(", ")

        # 主键的 Identity 需要作为 mapped_column 的独立位置参数
        if identity_arg and not type_extra:
            type_call = f"sa.{sa_type}, {identity_arg}"
        elif type_args:
            type_call = f"sa.{sa_type}({type_args})"
        else:
            type_call = f"sa.{sa_type}"

        lines.append(f"    {field_name}: Mapped[{python_type(sa_type)}] = mapped_column(")
        lines.append(f"        {type_call},")
        if kwargs_str:
            lines.append(f"        {kwargs_str},")
        lines.append("    )")

    # 表级唯一约束 + schema
    table_args: list[str] = []
    for uk_name, cols in unique_constraints.items():
        cols_str = ", ".join([repr(c) for c in cols])
        table_args.append(f"        sa.UniqueConstraint({cols_str}, name={repr(uk_name)}),")
    table_args.append('        {"schema": "oa"},')

    if table_args:
        lines.append("")
        lines.append("    __table_args__ = (")
        lines.extend(table_args)
        lines.append("    )")

    lines.append("")
    return "\n".join(lines)


def pg_type_to_excel(pg_type: str, char_len, numeric_precision, numeric_scale) -> str:
    """把 PostgreSQL 原生类型转换为 Excel 中使用的类型字符串。"""
    pg_type = pg_type.lower()
    if pg_type == "bigint":
        return "BIGINT"
    if pg_type == "integer":
        return "INTEGER"
    if pg_type == "smallint":
        return "SMALLINT"
    if pg_type == "boolean":
        return "BOOLEAN"
    if pg_type in ("character varying", "varchar"):
        return f"VARCHAR({char_len})" if char_len else "VARCHAR(255)"
    if pg_type in ("character", "char"):
        return f"CHAR({char_len})" if char_len else "CHAR(1)"
    if pg_type == "text":
        return "TEXT"
    if pg_type in ("timestamp with time zone", "timestamptz"):
        return "TIMESTAMP WITH TIME ZONE"
    if pg_type in ("timestamp without time zone", "timestamp"):
        return "TIMESTAMP WITH TIME ZONE"
    if pg_type == "date":
        return "DATE"
    if pg_type == "numeric":
        p = numeric_precision or 16
        s = numeric_scale or 2
        return f"NUMERIC({p},{s})"
    if pg_type == "decimal":
        p = numeric_precision or 16
        s = numeric_scale or 2
        return f"NUMERIC({p},{s})"
    if pg_type in ("json", "jsonb"):
        return "JSONB"
    if pg_type == "uuid":
        return "VARCHAR(36)"
    return pg_type.upper()


def fetch_view_columns_from_db(view_name: str) -> pd.DataFrame:
    """从数据库读取视图列信息，构造与 Excel 06 sheet 结构一致的 DataFrame。"""
    engine = create_engine(settings.database_url_with_search_path, future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    c.column_name,
                    c.data_type,
                    c.character_maximum_length,
                    c.numeric_precision,
                    c.numeric_scale,
                    pg_catalog.col_description((c.table_schema || '.' || c.table_name)::regclass::oid, c.ordinal_position) as comment
                FROM information_schema.columns c
                WHERE c.table_schema = 'oa' AND c.table_name = :view_name
                ORDER BY c.ordinal_position
            """),
            {"view_name": view_name},
        ).mappings().all()

    if not rows:
        raise ValueError(f"视图 {view_name} 在数据库中不存在或无字段")

    data = []
    for idx, row in enumerate(rows, start=1):
        data.append({
            "表名": view_name,
            "中文表名": view_name,
            "字段名": row["column_name"],
            "中文字段名": row["column_name"],
            "数据类型": pg_type_to_excel(
                row["data_type"],
                row["character_maximum_length"],
                row["numeric_precision"],
                row["numeric_scale"],
            ),
            "字段注释": row["comment"] or "",
            "字段序号": idx,
        })
    return pd.DataFrame(data)


def generate_view_model_code(view_name: str, fields_df: pd.DataFrame, pk_columns: list[str]) -> str:
    """为单个视图生成 SQLAlchemy 只读模型代码（使用 Table 直接映射视图）。"""
    class_name = "".join([part.capitalize() for part in view_name.split("_")])
    cn_name = str(fields_df["中文表名"].iloc[0])

    lines: list[str] = []
    lines.append(f"class {class_name}(Base):")
    lines.append(f'    """{cn_name}"""')
    lines.append(f'    __table__ = sa.Table(')
    lines.append(f'        "{view_name}",')
    lines.append("        Base.metadata,")

    for _, row in fields_df.iterrows():
        field_name = str(row["字段名"]).strip()
        data_type = str(row["数据类型"]).strip()
        comment = str(row["字段注释"]).strip() if pd.notna(row["字段注释"]) else ""

        sa_type, type_kwargs = map_column_type(data_type)
        is_pk = field_name in pk_columns

        # 构造 type 调用
        type_args = ", ".join(
            [f"{k}={repr(v) if isinstance(v, str) else v}" for k, v in type_kwargs.items()]
        )
        type_call = f"sa.{sa_type}({type_args})" if type_args else f"sa.{sa_type}"

        kwargs_parts: list[str] = []
        if comment:
            kwargs_parts.append(f"comment={repr(comment)}")
        if is_pk:
            kwargs_parts.append("primary_key=True")

        kwargs_str = ", ".join(kwargs_parts)

        if kwargs_str:
            lines.append(f'        sa.Column("{field_name}", {type_call}, {kwargs_str}),')
        else:
            lines.append(f'        sa.Column("{field_name}", {type_call}),')

    lines.append('        schema="oa",')
    lines.append('        info={"is_view": True},')
    lines.append("    )")
    lines.append("")
    return "\n".join(lines)


def python_type(sa_type: str) -> str:
    mapping = {
        "BigInteger": "int",
        "Integer": "int",
        "SmallInteger": "int",
        "Boolean": "bool",
        "String": "str",
        "Text": "str",
        "DateTime": "datetime",
        "Date": "date",
        "Numeric": "Decimal",
        "JSON": "dict",
    }
    return mapping.get(sa_type, "Any")


def main() -> int:
    parser = argparse.ArgumentParser(description="从 Excel 生成 SQLAlchemy 模型")
    parser.add_argument(
        "--only-new",
        action="store_true",
        help="只生成尚未存在的 domain 模型文件，避免覆盖已有手工补充字段的文件",
    )
    args = parser.parse_args()
    only_new = getattr(args, "only_new", False)

    if not EXCEL_PATH.exists():
        print(f"Excel 文件不存在: {EXCEL_PATH}", file=sys.stderr)
        return 1

    # 读取视图主键配置
    if not VIEW_METADATA_PATH.exists():
        print(f"视图主键配置不存在: {VIEW_METADATA_PATH}", file=sys.stderr)
        return 1
    view_metadata = json.loads(VIEW_METADATA_PATH.read_text(encoding="utf-8"))

    # 读取数据字典
    df_fields = pd.read_excel(EXCEL_PATH, sheet_name="06_全字段数据字典", header=0)

    # 保留第 1-10 阶段表 + 统计分析源表
    df_tables = df_fields[df_fields["表名"].isin(PHASE_1_10_TABLES)].copy()

    # 按业务域分组
    domain_tables: dict[str, list[str]] = {}
    for table in PHASE_1_10_TABLES:
        domain = DOMAIN_FILES.get(table)
        if not domain:
            print(f"表 {table} 未映射到模型文件", file=sys.stderr)
            return 1
        domain_tables.setdefault(domain, []).append(table)

    generated: dict[str, list[str]] = {}
    skipped: dict[str, list[str]] = {}
    for domain, tables in domain_tables.items():
        file_path = OUTPUT_DIR / f"{domain}.py"
        if only_new and file_path.exists():
            skipped[domain] = tables
            continue

        file_lines: list[str] = []
        file_lines.append("\"\"\"Generated by scripts/generate_models_from_excel.py\"\"\"")
        file_lines.append("from datetime import datetime, date")
        file_lines.append("from decimal import Decimal")
        file_lines.append("from typing import Optional")
        file_lines.append("")
        file_lines.append("import sqlalchemy as sa")
        file_lines.append("from sqlalchemy.orm import Mapped, mapped_column")
        file_lines.append("")
        file_lines.append("from app.models.base import Base, AuditMixin, SoftDeleteMixin")
        file_lines.append("")
        file_lines.append("")

        for table in tables:
            table_df = df_tables[df_tables["表名"] == table].sort_values("字段序号")
            file_lines.append(generate_model_code(table, table_df))

        file_path.write_text("\n".join(file_lines), encoding="utf-8")
        generated[domain] = tables
        print(f"Generated {file_path} with {len(tables)} tables")

    if skipped:
        print("\nSkipped existing files (use without --only-new to regenerate):")
        for domain, tables in sorted(skipped.items()):
            print(f"  {domain}: {', '.join(tables)}")

    # 生成第11阶段视图模型
    df_views = df_fields[df_fields["表名"].isin(PHASE_11_VIEWS)].copy()
    view_file_path = OUTPUT_DIR / f"{VIEWS_FILE}.py"
    if not (only_new and view_file_path.exists()):
        view_lines: list[str] = []
        view_lines.append('\"\"\"Generated by scripts/generate_models_from_excel.py')
        view_lines.append('第11阶段统计视图模型。')
        view_lines.append('视图只读，不继承 AuditMixin / SoftDeleteMixin。')
        view_lines.append('\"\"\"')
        view_lines.append("from datetime import datetime, date")
        view_lines.append("from decimal import Decimal")
        view_lines.append("from typing import Optional")
        view_lines.append("")
        view_lines.append("import sqlalchemy as sa")
        view_lines.append("")
        view_lines.append("from app.models.base import Base")
        view_lines.append("")
        view_lines.append("")
        view_lines.append("VIEW_NAMES = (")
        for view in PHASE_11_VIEWS:
            view_lines.append(f'    "{view}",')
        view_lines.append(")")
        view_lines.append("")
        view_lines.append("")

        for view in PHASE_11_VIEWS:
            view_df = df_views[df_views["表名"] == view].sort_values("字段序号")
            if view_df.empty:
                print(f"视图 {view} 在 Excel 中未找到字段定义，尝试从数据库读取...")
                try:
                    view_df = fetch_view_columns_from_db(view)
                except Exception as exc:
                    print(f"从数据库读取视图 {view} 失败: {exc}", file=sys.stderr)
                    return 1
            pk_columns = view_metadata.get(view, [])
            view_lines.append(generate_view_model_code(view, view_df, pk_columns))

        view_file_path.write_text("\n".join(view_lines), encoding="utf-8")
        generated[VIEWS_FILE] = PHASE_11_VIEWS
        print(f"Generated {view_file_path} with {len(PHASE_11_VIEWS)} views")
    else:
        skipped[VIEWS_FILE] = list(PHASE_11_VIEWS)
        print(f"Skipped existing {view_file_path}")

    # 更新 __init__.py：合并已存在和新生成的 domain
    init_path = OUTPUT_DIR / "__init__.py"
    existing_imports = set()
    if init_path.exists():
        for line in init_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("from app.models."):
                existing_imports.add(line)

    init_lines = [
        "from app.models.base import Base, AuditMixin, SoftDeleteMixin",
        "",
    ]
    all_domains = sorted(set(generated.keys()) | {d for d in DOMAIN_FILES.values()} | {VIEWS_FILE})
    for domain in all_domains:
        line = f"from app.models.{domain} import *  # noqa: F401,F403"
        if line not in existing_imports:
            existing_imports.add(line)
        init_lines.append(line)
    init_path.write_text("\n".join(init_lines) + "\n", encoding="utf-8")
    print(f"Updated {init_path}")

    # 汇总
    total_tables = sum(len(t) for d, t in generated.items() if d != VIEWS_FILE)
    total_views = len(generated.get(VIEWS_FILE, []))
    print(f"\nTotal tables generated: {total_tables}")
    print(f"Total views generated: {total_views}")
    for domain, tables in sorted(generated.items()):
        print(f"  {domain}: {', '.join(tables)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
