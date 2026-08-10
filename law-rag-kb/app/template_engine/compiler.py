from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import zipfile

from lxml import etree

from app.template_engine.schema import TemplateSchema

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"


class TemplateCompileError(RuntimeError):
    pass


def _signature(path: Path) -> str:
    head = path.read_bytes()[:8]
    if head.startswith(b"PK"):
        return "ooxml"
    if head.startswith(bytes.fromhex("D0CF11E0")):
        return "ole_doc"
    return "unknown"


def inspect_template(path: str | Path) -> dict:
    source = Path(path)
    source_format = _signature(source)
    report = {
        "path": str(source),
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "file_size": source.stat().st_size,
        "source_format": source_format,
        "table_count": 0,
        "content_control_count": 0,
        "bookmark_count": 0,
        "merge_marker_count": 0,
        "checkbox_symbol_count": 0,
    }
    if source_format != "ooxml":
        return report
    with zipfile.ZipFile(source) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    text = "".join(root.xpath("//w:t/text()", namespaces=NS))
    report.update(
        table_count=len(root.xpath("//w:tbl", namespaces=NS)),
        content_control_count=len(root.xpath("//w:sdt", namespaces=NS)),
        bookmark_count=len(root.xpath("//w:bookmarkStart", namespaces=NS)),
        merge_marker_count=len(root.xpath("//w:gridSpan|//w:vMerge", namespaces=NS)),
        checkbox_symbol_count=sum(text.count(symbol) for symbol in ("□", "☐", "√")),
    )
    return report


def _paragraph_text(paragraph) -> str:
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))


def _party_binding_candidates(field_id: str, candidates: list) -> list:
    """Resolve party fields by semantic row context, not global anchor ordinal.

    Complaint templates repeat labels such as “姓名” and “联系电话” in party,
    organization and litigation-agent rows. Global occurrence indexes are
    brittle and previously placed defendant data in the agent row.
    """
    parts = field_id.split(".")
    if len(parts) != 3 or parts[0] != "party":
        return candidates
    _, role, suffix = parts
    role_markers = {
        "plaintiff": ("原告", "申请人", "起诉人"),
        "defendant": ("被告", "被申请人"),
        "third_party": ("第三人",),
    }.get(role)
    if not role_markers:
        return candidates
    organization_field = suffix in {
        "organization_name",
        "organization_address",
        "organization_registration_address",
        "organization_phone",
        "unified_social_credit_code",
        "legal_representative",
    }
    selected = []
    for paragraph in candidates:
        rows = paragraph.xpath("ancestor::w:tr[1]", namespaces=NS)
        if not rows:
            continue
        row_text = "".join(rows[0].xpath(".//w:t/text()", namespaces=NS))
        if not any(marker in row_text for marker in role_markers):
            continue
        if "委托诉讼代理人" in row_text or "委托代理人" in row_text:
            continue
        organization_row = any(
            marker in row_text
            for marker in (
                "法人",
                "非法人组织",
                "行政机关",
                "授权的组织",
                "单位名称",
                "统一社会信用代码",
            )
        )
        natural_row = "自然人" in row_text
        if organization_field and not organization_row:
            continue
        if not organization_field and organization_row and not natural_row:
            continue
        selected.append(paragraph)
    return selected or candidates


def _existing_tags(root) -> set[str]:
    return set(root.xpath("//w:sdtPr/w:tag/@w:val", namespaces=NS))


def _normalize_layout_noise(
    root,
    *,
    enabled: bool,
    remove_explicit_page_breaks: bool = False,
) -> dict[str, int]:
    """Remove generator artifacts that create blank pages in the working copy.

    The supplied private-lending template carries pageBreakBefore on almost every
    paragraph plus five empty intermediate section properties.  They are not
    semantic formatting and produce empty pages in both Word and LibreOffice.
    The original file is never changed; only the normalized copy is cleaned.

    IMPORTANT: intermediate w:pPr/w:sectPr carry their own pgMar (page margins)
    that differ from the document-level sectPr.  Removing them collapses all
    sections into the single document-level sectPr whose margins may be wider.
    To preserve the per-section margins, we copy the pgMar from the first
    intermediate sectPr onto the document-level sectPr before removing them.
    """
    if not enabled:
        return {
            "removed_page_break_before": 0,
            "removed_intermediate_sections": 0,
            "removed_explicit_page_breaks": 0,
        }
    page_breaks = root.xpath("//w:pPr/w:pageBreakBefore", namespaces=NS)
    for node in page_breaks:
        node.getparent().remove(node)
    intermediate_sections = root.xpath("//w:pPr/w:sectPr", namespaces=NS)
    # Before removing intermediate sections, copy their pgMar to the
    # document-level sectPr to preserve the per-section page margins.
    if intermediate_sections:
        doc_sectPr = root.find(f".//{W}body/{W}sectPr")
        if doc_sectPr is not None:
            first_intermediate = intermediate_sections[0]
            for child_name in ("pgMar", "pgSz", "cols", "docGrid"):
                source = first_intermediate.find(f"{W}{child_name}")
                if source is None:
                    continue
                target = doc_sectPr.find(f"{W}{child_name}")
                if target is None:
                    doc_sectPr.append(deepcopy(source))
                else:
                    doc_sectPr.replace(target, deepcopy(source))
    for node in intermediate_sections:
        node.getparent().remove(node)
    explicit_page_breaks = (
        [
            node
            for node in root.xpath("//w:br", namespaces=NS)
            if node.get(W + "type") == "page"
        ]
        if remove_explicit_page_breaks
        else []
    )
    for node in explicit_page_breaks:
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)
    return {
        "removed_page_break_before": len(page_breaks),
        "removed_intermediate_sections": len(intermediate_sections),
        "removed_explicit_page_breaks": len(explicit_page_breaks),
    }


def _new_inline_control(tag_value: str, sample_run) -> etree._Element:
    sdt = etree.Element(W + "sdt")
    props = etree.SubElement(sdt, W + "sdtPr")
    alias = etree.SubElement(props, W + "alias")
    alias.set(W + "val", tag_value)
    tag = etree.SubElement(props, W + "tag")
    tag.set(W + "val", tag_value)
    # Keep this as a rich-text content control.  Word can hang during fixed-format
    # export when an inline plain-text SDT declares multiLine=1 inside a table cell.
    # Rich-text SDTs accept the line-break runs emitted by renderer.py and remain
    # stable in both Word and LibreOffice.
    content = etree.SubElement(sdt, W + "sdtContent")
    run = etree.SubElement(content, W + "r")
    if sample_run is not None:
        rpr = sample_run.find(W + "rPr")
        if rpr is not None:
            run.append(deepcopy(rpr))
    text = etree.SubElement(run, W + "t")
    text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text.text = ""
    return sdt


def _binding_target_paragraph(paragraph, binding: dict):
    offset = int(binding.get("target_cell_offset", 0))
    if not offset and not binding.get("append_paragraph"):
        return paragraph
    if offset:
        source_cells = paragraph.xpath("ancestor::w:tc[1]", namespaces=NS)
        source_rows = paragraph.xpath("ancestor::w:tr[1]", namespaces=NS)
        if not source_cells or not source_rows:
            return None
        source_cell = source_cells[0]
        cells = source_rows[0].xpath("./w:tc", namespaces=NS)
        try:
            target_cell = cells[cells.index(source_cell) + offset]
        except (ValueError, IndexError):
            return None
    else:
        source_cells = paragraph.xpath("ancestor::w:tc[1]", namespaces=NS)
        if not source_cells:
            return None
        target_cell = source_cells[0]
    if binding.get("append_paragraph"):
        target = etree.Element(W + "p")
        paragraph_props = paragraph.find(W + "pPr")
        if paragraph_props is not None:
            target.append(deepcopy(paragraph_props))
        target_cell.append(target)
        return target
    paragraphs = target_cell.xpath(".//w:p", namespaces=NS)
    paragraph_index = int(binding.get("target_paragraph", 0))
    return paragraphs[paragraph_index] if paragraph_index < len(paragraphs) else None


def _insert_control(paragraph, tag_value: str, *, anchor: str | None = None) -> None:
    sample_runs = paragraph.xpath("./w:r", namespaces=NS)
    control = _new_inline_control(tag_value, sample_runs[-1] if sample_runs else None)
    if not anchor:
        paragraph.append(control)
        return
    text_nodes = paragraph.xpath(".//w:t[not(ancestor::w:sdt)]", namespaces=NS)
    for node in text_nodes:
        text = node.text or ""
        position = text.find(anchor)
        if position < 0:
            continue
        split_at = position + len(anchor)
        run = node.getparent()
        if run is None or run.tag != W + "r":
            break
        suffix = text[split_at:]
        node.text = text[:split_at]
        run_index = paragraph.index(run)
        paragraph.insert(run_index + 1, control)
        if suffix:
            suffix_run = deepcopy(run)
            suffix_nodes = suffix_run.xpath(".//w:t", namespaces=NS)
            if suffix_nodes:
                suffix_nodes[0].text = suffix
                suffix_nodes[0].set(
                    "{http://www.w3.org/XML/1998/namespace}space", "preserve"
                )
                for extra in suffix_nodes[1:]:
                    extra.text = ""
                paragraph.insert(run_index + 2, suffix_run)
        return
    paragraph.append(control)


def _insert_semantic_marker(
    tables: list,
    existing: set[str],
    *,
    tag_value: str,
    binding: dict,
) -> bool:
    if tag_value in existing:
        return True
    table_index = int(binding.get("table_index", -1))
    anchor = str(binding.get("anchor") or "")
    occurrence = int(binding.get("occurrence", 0))
    if table_index < 0 or table_index >= len(tables) or not anchor:
        return False
    candidates = [
        paragraph
        for paragraph in tables[table_index].xpath(".//w:p", namespaces=NS)
        if anchor in _paragraph_text(paragraph)
    ]
    if occurrence >= len(candidates):
        return False
    paragraph = candidates[occurrence]
    target = _binding_target_paragraph(paragraph, binding)
    if target is None:
        return False
    _insert_control(
        target,
        tag_value,
        anchor=anchor if target is paragraph else None,
    )
    existing.add(tag_value)
    return True


def _validate_structured_bindings(tables: list, schema: TemplateSchema) -> None:
    errors: list[dict] = []
    for binding in schema.metadata.get("repeat_bindings") or []:
        if not binding.get("value_field"):
            continue
        group = str(binding.get("repeat_group") or binding.get("value_field"))
        table_index = int(binding.get("table_index", -1))
        if table_index < 0 or table_index >= len(tables):
            errors.append({"type": "repeat", "id": group, "reason": "table_not_found"})
            continue
        rows = tables[table_index].xpath("./w:tr", namespaces=NS)
        data_indices = [int(index) for index in binding.get("data_row_indices") or []]
        prototype_index = int(binding.get("prototype_row_index", -1))
        if not data_indices or any(index < 0 or index >= len(rows) for index in data_indices):
            errors.append({"type": "repeat", "id": group, "reason": "data_row_not_found"})
            continue
        if prototype_index < 0 or prototype_index >= len(rows):
            errors.append({"type": "repeat", "id": group, "reason": "prototype_row_not_found"})
            continue
        cells = rows[prototype_index].xpath("./w:tc", namespaces=NS)
        columns = binding.get("columns") or []
        if not columns or any(
            int(column.get("index", -1)) < 0
            or int(column.get("index", -1)) >= len(cells)
            for column in columns
        ):
            errors.append({"type": "repeat", "id": group, "reason": "column_not_found"})
        summary = binding.get("summary")
        if isinstance(summary, dict):
            summary_index = int(summary.get("row_index", -1))
            if summary_index < 0 or summary_index >= len(rows):
                errors.append({"type": "repeat", "id": group, "reason": "summary_row_not_found"})
    layout = schema.metadata.get("party_layout") or {}
    for block in layout.get("blocks") or []:
        role = str(block.get("role") or "")
        entity_type = str(block.get("entity_type") or "")
        table_index = int(block.get("table_index", -1))
        anchor = str(block.get("row_anchor") or "")
        if table_index < 0 or table_index >= len(tables):
            errors.append(
                {"type": "party_block", "id": f"{role}.{entity_type}", "reason": "table_not_found"}
            )
            continue
        matches = [
            row
            for row in tables[table_index].xpath("./w:tr", namespaces=NS)
            if anchor in "".join(row.xpath(".//w:t/text()", namespaces=NS))
        ]
        if not anchor or len(matches) != 1:
            errors.append(
                {
                    "type": "party_block",
                    "id": f"{role}.{entity_type}",
                    "reason": "row_anchor_not_unique",
                    "matches": len(matches),
                }
            )
    if errors:
        raise TemplateCompileError(f"structured render bindings invalid: {errors}")


def compile_template(
    source_path: str | Path,
    output_path: str | Path,
    schema: TemplateSchema,
) -> dict:
    source = Path(source_path)
    output = Path(output_path)
    inspection = inspect_template(source)
    if inspection["source_format"] != "ooxml":
        raise TemplateCompileError("TEMPLATE_INVALID_FORMAT: source must be OOXML DOCX")

    with zipfile.ZipFile(source) as archive:
        document_xml = archive.read("word/document.xml")
    root = etree.fromstring(document_xml)
    normalization = _normalize_layout_noise(
        root,
        enabled=bool(schema.metadata.get("normalize_layout_noise")),
        remove_explicit_page_breaks=bool(
            schema.metadata.get("remove_explicit_page_breaks")
        ),
    )
    tables = root.xpath("//w:tbl", namespaces=NS)
    _validate_structured_bindings(tables, schema)
    existing = _existing_tags(root)
    inserted: list[str] = []
    inserted_sections: list[str] = []
    inserted_repeats: list[str] = []
    unresolved: list[dict] = []

    for field in schema.fields:
        binding = field.binding
        tag_value = f"ld.field:{field.field_id}"
        if tag_value in existing:
            inserted.append(field.field_id)
            continue
        if binding.table_index >= len(tables):
            unresolved.append({"field_id": field.field_id, "reason": "table_not_found"})
            continue
        candidates = [
            paragraph
            for paragraph in tables[binding.table_index].xpath(".//w:p", namespaces=NS)
            if binding.anchor in _paragraph_text(paragraph)
        ]
        party_candidates = _party_binding_candidates(field.field_id, candidates)
        occurrence = 0 if party_candidates is not candidates else binding.occurrence
        candidates = party_candidates
        if occurrence >= len(candidates):
            unresolved.append(
                {
                    "field_id": field.field_id,
                    "reason": "anchor_not_found",
                    "anchor": binding.anchor,
                    "matches": len(candidates),
                }
            )
            continue
        paragraph = candidates[occurrence]
        target = _binding_target_paragraph(paragraph, binding.model_dump())
        if target is None:
            unresolved.append(
                {
                    "field_id": field.field_id,
                    "reason": "target_cell_not_found",
                    "anchor": binding.anchor,
                }
            )
            continue
        _insert_control(
            target,
            tag_value,
            anchor=binding.anchor if target is paragraph else None,
        )
        existing.add(tag_value)
        inserted.append(field.field_id)

    unresolved_semantic_markers: list[dict] = []
    for section_id, binding in (schema.metadata.get("section_bindings") or {}).items():
        if _insert_semantic_marker(
            tables,
            existing,
            tag_value=f"ld.section:{section_id}",
            binding=binding,
        ):
            inserted_sections.append(str(section_id))
        else:
            unresolved_semantic_markers.append(
                {"type": "section", "id": section_id, "binding": binding}
            )
    for binding in schema.metadata.get("repeat_bindings") or []:
        repeat_group = str(binding.get("repeat_group") or "")
        if repeat_group and _insert_semantic_marker(
            tables,
            existing,
            tag_value=f"ld.repeat:{repeat_group}",
            binding=binding,
        ):
            inserted_repeats.append(repeat_group)
        else:
            unresolved_semantic_markers.append(
                {"type": "repeat", "id": repeat_group, "binding": binding}
            )

    unresolved_required = [
        issue for issue in unresolved if issue["field_id"] in schema.required_fields
    ]
    if unresolved_required:
        raise TemplateCompileError(
            f"required render bindings unresolved: {unresolved_required}"
        )
    if unresolved_semantic_markers:
        raise TemplateCompileError(
            f"semantic render markers unresolved: {unresolved_semantic_markers}"
        )

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
        **inspection,
        "schema_id": schema.schema_id,
        "normalized_path": str(output),
        "inserted_fields": inserted,
        "inserted_sections": inserted_sections,
        "inserted_repeats": inserted_repeats,
        "unresolved_semantic_markers": unresolved_semantic_markers,
        "unresolved_fields": unresolved,
        "required_bindings_ok": not unresolved_required,
        **normalization,
        "normalized_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
