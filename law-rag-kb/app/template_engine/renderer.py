from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import re
import tempfile
from typing import Any
import zipfile

from lxml import etree

from app.template_engine.compiler import NS, W, TemplateCompileError
from app.template_engine.schema import TemplateSchema


def _display_value(value: Any, mode: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        if mode == "multiline":
            return "\n".join(
                f"{index}. {_display_value(item, 'text')}"
                for index, item in enumerate(value, start=1)
            )
        return "、".join(str(item) for item in value)
    if isinstance(value, dict):
        if value.get("evidence_name") or value.get("name"):
            name = value.get("evidence_name") or value.get("name")
            parts = [str(name)]
            if value.get("source") or value.get("source_from"):
                parts.append(f"来源：{value.get('source') or value.get('source_from')}")
            if value.get("page_no") or value.get("page"):
                parts.append(f"页码：{value.get('page_no') or value.get('page')}")
            if value.get("proof_purpose") or value.get("purpose"):
                parts.append(
                    f"证明目的：{value.get('proof_purpose') or value.get('purpose')}"
                )
            return "；".join(parts)
        return "；".join(
            f"{key}：{item}"
            for key, item in value.items()
            if item not in (None, "", [])
        )
    return str(value)


def _set_cell_text(cell: etree._Element, value: str, *, color_val: str | None = None) -> None:
    text_nodes = cell.xpath(".//w:t", namespaces=NS)
    if text_nodes:
        text_nodes[0].text = value
        text_nodes[0].set(
            "{http://www.w3.org/XML/1998/namespace}space", "preserve"
        )
        for node in text_nodes[1:]:
            node.text = ""
        if color_val and text_nodes:
            run = text_nodes[0].getparent()
            if run is not None and run.tag == W + "r":
                rpr = run.find(W + "rPr")
                if rpr is None:
                    rpr = etree.Element(W + "rPr")
                    run.insert(0, rpr)
                color = etree.SubElement(rpr, W + "color")
                color.set(W + "val", color_val)
        return
    paragraph = cell.find(W + "p")
    if paragraph is None:
        paragraph = etree.SubElement(cell, W + "p")
    run = etree.SubElement(paragraph, W + "r")
    if color_val:
        rpr = etree.SubElement(run, W + "rPr")
        color = etree.SubElement(rpr, W + "color")
        color.set(W + "val", color_val)
    text = etree.SubElement(run, W + "t")
    text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text.text = value


def _item_value(item: Any, *keys: str) -> str:
    if isinstance(item, dict):
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return str(value)
        return ""
    return str(item)


def _repeat_items(value: Any) -> list[Any]:
    if value in (None, "", []):
        return []
    return value if isinstance(value, list) else [value]


def _repeat_column_value(
    item: Any,
    column: dict[str, Any],
    item_index: int,
) -> str:
    keys = column.get("keys") or []
    if isinstance(keys, str):
        keys = [keys]
    if isinstance(item, dict):
        value = _item_value(item, *(str(key) for key in keys))
    else:
        value = str(item) if column.get("fallback") else ""
    if not value and column.get("auto_number"):
        value = str(item_index + 1)
    return value


def _populate_repeat_binding(
    table: etree._Element,
    binding: dict[str, Any],
    value: Any,
) -> int:
    items = _repeat_items(value)
    all_rows = table.xpath("./w:tr", namespaces=NS)
    data_row_indices = [int(index) for index in binding.get("data_row_indices") or []]
    prototype_index = int(binding.get("prototype_row_index", -1))
    if not data_row_indices or prototype_index < 0:
        return 0
    prototype = deepcopy(all_rows[prototype_index])
    rows = [all_rows[index] for index in data_row_indices]
    for row in rows:
        for cell in row.xpath("./w:tc", namespaces=NS):
            _set_cell_text(cell, "")
    while len(rows) < len(items):
        clone = deepcopy(prototype)
        table.append(clone)
        rows.append(clone)
    columns = binding.get("columns") or []
    for item_index, item in enumerate(items):
        cells = rows[item_index].xpath("./w:tc", namespaces=NS)
        for column in columns:
            cell_index = int(column.get("index", -1))
            if cell_index < 0 or cell_index >= len(cells):
                continue
            display = _repeat_column_value(item, column, item_index)
            color = "FF0000" if "【待补充" in display or "【冲突值" in display else None
            _set_cell_text(cells[cell_index], display, color_val=color)
    return len(items)


def _populate_repeat_summary(
    table: etree._Element,
    summary: dict[str, Any],
    values: dict[str, Any],
) -> None:
    row_index = int(summary.get("row_index", -1))
    rows = table.xpath("./w:tr", namespaces=NS)
    if row_index < 0 or row_index >= len(rows):
        return
    fields = summary.get("fields") or {}
    replacements = {}
    for alias, configured_fields in fields.items():
        candidates = (
            configured_fields
            if isinstance(configured_fields, list)
            else [configured_fields]
        )
        raw_value = next(
            (
                values.get(str(field_id))
                for field_id in candidates
                if values.get(str(field_id)) not in (None, "", [])
            ),
            None,
        )
        replacements[str(alias)] = (
            _display_value(raw_value, "text") or f"【待补充：{alias}】"
        )

    class Missing(dict):
        def __missing__(self, key: str) -> str:
            return f"【待补充：{key}】"

    display = str(summary.get("template") or "").format_map(Missing(replacements))
    cells = rows[row_index].xpath("./w:tc", namespaces=NS)
    if cells:
        color = "FF0000" if "【待补充" in display else None
        _set_cell_text(cells[0], display, color_val=color)


def _populate_repeat_groups(
    root: etree._Element, schema: TemplateSchema, values: dict[str, Any]
) -> dict[str, int]:
    tables = root.xpath("//w:tbl", namespaces=NS)
    populated: dict[str, int] = {}
    for binding in schema.metadata.get("repeat_bindings") or []:
        value_field = str(binding.get("value_field") or "")
        if not value_field:
            continue
        table_index = int(binding.get("table_index", -1))
        if table_index < 0 or table_index >= len(tables):
            continue
        table = tables[table_index]
        summary = binding.get("summary")
        if isinstance(summary, dict):
            _populate_repeat_summary(table, summary, values)
        repeat_group = str(binding.get("repeat_group") or value_field)
        populated[repeat_group] = _populate_repeat_binding(
            table,
            binding,
            values.get(value_field),
        )
    return populated


def _party_field_value(
    field: Any,
    record: dict[str, Any],
) -> Any:
    suffix = field.field_id.rsplit(".", 1)[-1]
    value = record.get(suffix)
    if value not in (None, "", []):
        return value
    should_mark_missing = (
        field.required_policy in {"required", "computed"}
        or field.missing_behavior != "blank"
    )
    if field.generation_policy != "user_only" and should_mark_missing:
        return f"【待补充：{field.label}】"
    return ""


def _fill_party_row(
    row: etree._Element,
    schema: TemplateSchema,
    role: str,
    record: dict[str, Any],
) -> None:
    field_by_id = {field.field_id: field for field in schema.fields}
    prefix = f"ld.field:party.{role}."
    for control in row.xpath(".//w:sdt", namespaces=NS):
        tags = control.xpath("./w:sdtPr/w:tag/@w:val", namespaces=NS)
        if not tags or not str(tags[0]).startswith(prefix):
            continue
        field_id = str(tags[0]).removeprefix("ld.field:")
        field = field_by_id.get(field_id)
        if field is None:
            continue
        value = _party_field_value(field, record)
        display = _display_value(value, field.binding.mode)
        if field.value_type == "date" and value:
            display = _format_date_and_clear_placeholder(control, value)
        if field.binding.mode == "checkbox" and value:
            changed = (
                _apply_gender_checkbox(control, value)
                if field_id.endswith(".gender")
                else False
            )
            if changed:
                display = ""
        color = "FF0000" if "【待补充" in display or "【冲突值" in display else None
        _replace_control_content(control, display, color_val=color)


def _populate_party_blocks(
    root: etree._Element,
    schema: TemplateSchema,
    values: dict[str, Any],
) -> dict[str, int]:
    records_by_role = values.get("_party_records")
    layout = schema.metadata.get("party_layout") or {}
    blocks = layout.get("blocks") or []
    if not isinstance(records_by_role, dict) or not blocks:
        return {}
    tables = root.xpath("//w:tbl", namespaces=NS)
    populated: dict[str, int] = {}
    for block in blocks:
        role = str(block.get("role") or "")
        entity_type = str(block.get("entity_type") or "")
        table_index = int(block.get("table_index", -1))
        row_anchor = str(block.get("row_anchor") or "")
        if table_index < 0 or table_index >= len(tables) or not row_anchor:
            continue
        records = [
            record
            for record in records_by_role.get(role, [])
            if record.get("entity_type") == entity_type
        ]
        if not records:
            continue
        candidates = [
            row
            for row in tables[table_index].xpath("./w:tr", namespaces=NS)
            if row_anchor in "".join(row.xpath(".//w:t/text()", namespaces=NS))
        ]
        if not candidates:
            continue
        prototype = candidates[0]
        rows = [prototype]
        parent = prototype.getparent()
        insert_at = parent.index(prototype) + 1
        for _ in records[1:]:
            clone = deepcopy(prototype)
            parent.insert(insert_at, clone)
            rows.append(clone)
            insert_at += 1
        for row, record in zip(rows, records):
            _fill_party_row(row, schema, role, record)
        populated[f"{role}.{entity_type}"] = len(records)
    return populated


def _replace_control_content(control, value: str, *, color_val: str | None = None) -> None:
    content = control.find(W + "sdtContent")
    if content is None:
        content = etree.SubElement(control, W + "sdtContent")
    sample_rpr = content.find(".//" + W + "rPr")
    for child in list(content):
        content.remove(child)
    lines = value.splitlines() or [""]
    for index, line in enumerate(lines):
        run = etree.SubElement(content, W + "r")
        rpr = deepcopy(sample_rpr) if sample_rpr is not None else etree.Element(W + "rPr")
        if color_val:
            color = etree.SubElement(rpr, W + "color")
            color.set(W + "val", color_val)
        if len(rpr):
            run.append(rpr)
        if index:
            etree.SubElement(run, W + "br")
        text = etree.SubElement(run, W + "t")
        text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        text.text = line


def _apply_delivery_checkbox(control: etree._Element, value: Any) -> bool:
    paragraph = control.getparent()
    if paragraph is None or paragraph.tag != W + "p":
        return False
    selected = str(value or "").strip()
    if "现金" in selected:
        choice = "cash"
    elif "转账" in selected or "银行" in selected:
        choice = "transfer"
    else:
        choice = "other"
    changed = False
    for node in paragraph.xpath(".//w:t[not(ancestor::w:sdt)]", namespaces=NS):
        text = node.text or ""
        updated = text.replace("现金☒", "现金□").replace("现金☑", "现金□").replace("转账☒", "转账□").replace("转账☑", "转账□")
        if choice == "cash":
            updated = updated.replace("现金□", "现金☑")
        elif choice == "transfer":
            updated = updated.replace("转账□", "转账☑")
        if updated != text:
            node.text = updated
            changed = True
    return changed


# Wingdings 复选框符号：0xA8=空框 ☐，0xFE=勾选框 ☑（部分模板用 <w:sym> 而非文本 □）。
_WINGDINGS_EMPTY = "00A8"
_WINGDINGS_CHECKED = "00FE"


def _tick_wingdings_checkbox(option_run: etree._Element) -> bool:
    """把“男/女”文字 run 同行内最近的空 <w:sym> 框（0xA8）改为勾选框（0xFE）。"""
    parent = option_run.getparent()
    if parent is None:
        return False
    runs = list(parent)
    try:
        index = runs.index(option_run)
    except ValueError:
        return False
    # 先向后找（框常在选项文字后），再向前找。
    candidates = list(runs[index + 1 :]) + list(reversed(runs[:index]))
    for sibling in candidates:
        if sibling.tag != W + "r":
            continue
        text = "".join(sibling.xpath(".//w:t/text()", namespaces=NS)).strip()
        if text in ("男", "女"):
            return False  # 已到下一选项，停止
        sym = sibling.find(W + "sym")
        if sym is not None and (sym.get(W + "char") or "").upper() == _WINGDINGS_EMPTY:
            sym.set(W + "char", _WINGDINGS_CHECKED)
            return True
    return False


def _apply_gender_checkbox(control: etree._Element, value: Any) -> bool:
    paragraph = control.getparent()
    if paragraph is None or paragraph.tag != W + "p":
        return False
    selected = str(value or "").strip().casefold()
    if selected in {"男", "male", "m"}:
        choice = "男"
    elif selected in {"女", "female", "f"}:
        choice = "女"
    else:
        return False
    # 路径一：文本 □ 形态（离婚/机动车/物业等），勾选=把对应 男□/女□ 改为 ☑。
    boxes = "□☐☑☒√"
    text_changed = False
    for node in paragraph.xpath(".//w:t[not(ancestor::w:sdt)]", namespaces=NS):
        text = node.text or ""
        if "男" not in text and "女" not in text:
            continue
        updated = text
        for opt in ("男", "女"):
            for box in boxes:
                updated = re.sub(f"{opt}\\s*{re.escape(box)}", f"{opt}□", updated)
                updated = re.sub(f"{re.escape(box)}\\s*{opt}", f"□{opt}", updated)
        new_text = re.sub(f"{choice}\\s*□", f"{choice}☑", updated)
        if new_text != updated:
            text_changed = True
            updated = new_text
        if updated != text:
            node.text = updated
            text_changed = True
    if text_changed:
        return True
    # 路径二：<w:sym> Wingdings 形态（租赁/买卖等），勾选=把对应选项的空框符号改为勾框。
    for run in paragraph.xpath("./w:r", namespaces=NS):
        if choice in run.xpath(".//w:t/text()", namespaces=NS):
            return _tick_wingdings_checkbox(run)
    return False


def _format_date_and_clear_placeholder(
    control: etree._Element, value: Any
) -> str:
    display = str(value or "").strip()
    matched = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", display)
    if matched:
        year, month, day = matched.groups()
        display = f"{year}年{int(month)}月{int(day)}日"
    paragraph = control.getparent()
    if paragraph is not None and paragraph.tag == W + "p":
        after_control = False
        for child in paragraph:
            if child is control:
                after_control = True
                continue
            if not after_control:
                continue
            for node in child.xpath(".//w:t", namespaces=NS):
                text = node.text or ""
                if "民族：" in text:
                    node.text = re.sub(r"^[\s年月日]+", "", text)
                elif re.fullmatch(r"[\s年月日]*", text):
                    node.text = ""
                else:
                    node.text = re.sub(r"^\s*年\s+月\s+日\s*", "", text)
    return display

def _clear_user_only_placeholders(root: etree._Element) -> list[str]:
    """Remove template implementation markers that a model must never fill."""
    cleared: list[str] = []
    for marker in ("{pic_qmPath}",):
        marker_count = 0
        for node in root.xpath("//w:t", namespaces=NS):
            value = node.text or ""
            if marker not in value:
                continue
            marker_count += value.count(marker)
            node.text = value.replace(marker, "")
        cleared.extend([marker] * marker_count)
    return cleared


def render_template(
    normalized_path: str | Path,
    output_path: str | Path,
    schema: TemplateSchema,
    values: dict[str, Any],
) -> dict:
    source = Path(normalized_path)
    output = Path(output_path)
    values = dict(values)
    with zipfile.ZipFile(source) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))

    controls = {
        tags[0]: control
        for control in root.xpath("//w:sdt", namespaces=NS)
        if (tags := control.xpath("./w:sdtPr/w:tag/@w:val", namespaces=NS))
    }
    missing_bindings: list[str] = []
    empty_required: list[str] = []
    filled: list[str] = []
    checkbox_fields: list[str] = []
    evidence_policy = (schema.metadata or {}).get("evidence_directory") or {}
    externalized_fields = {
        str(evidence_policy.get("source_field"))
    } if (
        evidence_policy.get("enabled") is True
        and evidence_policy.get("inline_mode") == "blank"
        and evidence_policy.get("source_field")
    ) else set()
    for field_id in externalized_fields:
        values[field_id] = []
    for field in schema.fields:
        tag = f"ld.field:{field.field_id}"
        control = controls.get(tag)
        if control is None:
            missing_bindings.append(field.field_id)
            continue
        if field.field_id in externalized_fields:
            _replace_control_content(control, "")
            filled.append(field.field_id)
            continue
        value = values.get(field.field_id)
        if field.field_id in schema.required_fields and value in (None, "", []):
            empty_required.append(field.field_id)
        if value not in (None, "", []):
            display = _display_value(value, field.binding.mode)
            if field.field_id == "loan.delivery.items":
                cells = control.xpath("ancestor::w:tc[1]", namespaces=NS)
                if cells:
                    cell_color = "FF0000" if "【待补充" in display or "【冲突值" in display else None
                    _set_cell_text(cells[0], display, color_val=cell_color)
                    filled.append(field.field_id)
                    continue
            if field.value_type == "date":
                display = _format_date_and_clear_placeholder(control, value)
            if field.binding.mode == "checkbox":
                changed = (
                    _apply_gender_checkbox(control, value)
                    if field.field_id.endswith(".gender")
                    else _apply_delivery_checkbox(control, value)
                )
                if changed:
                    checkbox_fields.append(field.field_id)
                    display = ""
            color_val = "FF0000" if "【待补充" in display or "【冲突值" in display else None
            _replace_control_content(control, display, color_val=color_val)
            filled.append(field.field_id)

    if missing_bindings:
        raise TemplateCompileError(f"normalized template missing controls: {missing_bindings}")
    if empty_required:
        raise TemplateCompileError(f"required values missing: {empty_required}")

    cleared_user_only_placeholders = _clear_user_only_placeholders(root)
    repeat_rows_populated = _populate_repeat_groups(root, schema, values)
    party_rows_populated = _populate_party_blocks(root, schema, values)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        suffix=".docx", dir=output.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(source) as src, zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED
        ) as dst:
            for item in src.infolist():
                content = (
                    etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                    if item.filename == "word/document.xml"
                    else src.read(item.filename)
                )
                dst.writestr(item, content)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)

    return {
        "schema_id": schema.schema_id,
        "output_path": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "filled_fields": filled,
        "checkbox_fields": checkbox_fields,
        "repeat_rows_populated": repeat_rows_populated,
        "party_rows_populated": party_rows_populated,
        "empty_required_fields": empty_required,
        "unreplaced_placeholder_count": 0,
        "cleared_user_only_placeholders": cleared_user_only_placeholders,
    }
