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


def _populate_repeat_table(
    table: etree._Element,
    items: list[Any],
    *,
    column_count: int,
    objection_mode: bool,
) -> int:
    rows = [
        row
        for row in table.xpath("./w:tr", namespaces=NS)[1:]
        if len(row.xpath("./w:tc", namespaces=NS)) >= column_count
    ]
    if not rows or not items:
        return 0
    while len(rows) < len(items):
        clone = deepcopy(rows[-1])
        table.append(clone)
        rows.append(clone)
    for index, item in enumerate(items):
        cells = rows[index].xpath("./w:tc", namespaces=NS)
        number = _item_value(item, "number", "evidence_no") or str(index + 1)
        _set_cell_text(cells[0], number)
        if objection_mode:
            _set_cell_text(cells[1], _item_value(item, "evidence_name", "name"))
            _set_cell_text(cells[2], _item_value(item, "authenticity"))
            _set_cell_text(cells[3], _item_value(item, "legality"))
            _set_cell_text(cells[4], _item_value(item, "relevance"))
            _set_cell_text(
                cells[5],
                _item_value(item, "probative_force", "objection", "opinion")
                or (str(item) if not isinstance(item, dict) else ""),
            )
        else:
            _set_cell_text(cells[1], _item_value(item, "page_no", "page"))
            _set_cell_text(cells[2], _item_value(item, "evidence_name", "name") or str(item))
            _set_cell_text(cells[3], _item_value(item, "source", "source_from"))
            _set_cell_text(cells[4], _item_value(item, "proof_purpose", "purpose"))
    return len(items)


def _populate_repeat_groups(
    root: etree._Element, schema: TemplateSchema, values: dict[str, Any]
) -> dict[str, int]:
    if schema.template_code != "civil_defense.trademark_infringement":
        return {}
    tables = root.xpath("//w:tbl", namespaces=NS)
    if len(tables) < 3:
        return {}
    own = values.get("document.evidence_list") or []
    objections = values.get("document.opponent_evidence_objections") or []
    return {
        "own_evidence_items": _populate_repeat_table(
            tables[1], list(own), column_count=5, objection_mode=False
        ),
        "opponent_evidence_items": _populate_repeat_table(
            tables[2], list(objections), column_count=6, objection_mode=True
        ),
    }


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
    for field in schema.fields:
        tag = f"ld.field:{field.field_id}"
        control = controls.get(tag)
        if control is None:
            missing_bindings.append(field.field_id)
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
        "empty_required_fields": empty_required,
        "unreplaced_placeholder_count": 0,
        "cleared_user_only_placeholders": cleared_user_only_placeholders,
    }
