"""结构化文档解析：PDF / DOCX / TXT / Markdown / 常见图片。"""
from io import BytesIO
from pathlib import Path

import fitz
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from PIL import Image, UnidentifiedImageError

from app.ingest.document import ContentNode, ImageAsset, ParsedDocument, TextBlock


class UnsupportedFileTypeError(Exception):
    """不支持的文件类型（调用方应判为 SKIPPED 而非 FAILED）。"""


_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"}


def from_text(text: str) -> ParsedDocument:
    """把数据库中的 content_text 包装为结构化文档。"""
    blocks = [TextBlock(text=text, page_no=None, order=0)] if text.strip() else []
    return ParsedDocument(
        text_blocks=blocks,
        nodes=[ContentNode(kind="text", text=text, page_no=None, order=0)] if blocks else [],
        metadata={"source": "content_text", "page_count": None},
    )


def parse(
    content: bytes,
    file_ext: str,
    *,
    scan_page_min_text_chars: int = 40,
    pdf_render_scale: float = 1.5,
) -> ParsedDocument:
    """按扩展名解析 bytes，保留文本块、图片、页码和顺序。"""
    ext = (file_ext or "").lower().lstrip(".")
    if ext == "pdf":
        return _parse_pdf(
            content,
            scan_page_min_text_chars=scan_page_min_text_chars,
            render_scale=pdf_render_scale,
        )
    if ext == "docx":
        return _parse_docx(content)
    if ext in ("txt", "md"):
        text = content.decode("utf-8", errors="replace")
        kind = "markdown" if ext == "md" else "text"
        return ParsedDocument(
            text_blocks=[TextBlock(text=text, page_no=None, order=0)],
            nodes=[ContentNode(kind=kind, text=text, page_no=None, order=0)],
            metadata={"file_type": ext, "page_count": None},
        )
    if ext in _IMAGE_EXTENSIONS:
        image = _make_image_asset(content, ext, page_no=1, image_index=0)
        return ParsedDocument(
            images=[image],
            nodes=[ContentNode(kind="image", order=0, page_no=1, image_sha256=image.sha256)],
            metadata={"file_type": ext, "page_count": 1},
        )
    raise UnsupportedFileTypeError(ext)


def _parse_pdf(
    content: bytes, *, scan_page_min_text_chars: int, render_scale: float
) -> ParsedDocument:
    doc = fitz.open(stream=content, filetype="pdf")
    text_blocks: list[TextBlock] = []
    images: list[ImageAsset] = []
    nodes: list[ContentNode] = []
    order = 0
    image_index = 0
    try:
        for zero_page, page in enumerate(doc):
            page_no = zero_page + 1
            raw_blocks = sorted(
                page.get_text("blocks"), key=lambda b: (round(float(b[1]), 1), float(b[0]))
            )
            page_text_parts: list[str] = []
            page_items: list[tuple[float, float, str, object]] = []
            for block in raw_blocks:
                if len(block) > 6 and int(block[6]) != 0:
                    # 图片由 get_images/extract_image 统一处理，避免把 <image:...> 当正文。
                    continue
                block_text = str(block[4] or "").strip()
                if not block_text:
                    continue
                page_text_parts.append(block_text)
                page_items.append((float(block[1]), float(block[0]), "text", block_text))

            page_text = "\n".join(page_text_parts).strip()
            nearby = page_text[:800]
            if len(page_text) < scan_page_min_text_chars:
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(render_scale, render_scale), alpha=False
                )
                image = _make_image_asset(
                    pix.tobytes("png"),
                    "png",
                    page_no=page_no,
                    image_index=image_index,
                    nearby_text=nearby,
                    is_page_scan=True,
                )
                images.append(image)
                page_items.append((0.0, 0.0, "image", image))
                image_index += 1
            else:
                seen_xrefs: set[int] = set()
                for image_info in page.get_images(full=True):
                    xref = int(image_info[0])
                    if xref in seen_xrefs:
                        continue
                    seen_xrefs.add(xref)
                    extracted = doc.extract_image(xref)
                    image_bytes = extracted.get("image")
                    if not image_bytes:
                        continue
                    image = _make_image_asset(
                        image_bytes,
                        str(extracted.get("ext") or "png"),
                        page_no=page_no,
                        image_index=image_index,
                        nearby_text=nearby,
                    )
                    images.append(image)
                    rects = page.get_image_rects(xref)
                    rect = rects[0] if rects else fitz.Rect(0, 0, 0, 0)
                    page_items.append((float(rect.y0), float(rect.x0), "image", image))
                    image_index += 1

            for _, _, kind, value in sorted(page_items, key=lambda item: (item[0], item[1])):
                if kind == "text":
                    text = str(value)
                    text_blocks.append(
                        TextBlock(text=text, page_no=page_no, order=order, kind="pdf_block")
                    )
                    nodes.append(ContentNode(kind="text", text=text, page_no=page_no, order=order))
                else:
                    image = value
                    nodes.append(
                        ContentNode(
                            kind="image",
                            page_no=page_no,
                            order=order,
                            image_sha256=image.sha256,
                        )
                    )
                order += 1
    finally:
        doc.close()
    return ParsedDocument(
        text_blocks=text_blocks,
        images=images,
        nodes=nodes,
        metadata={"file_type": "pdf", "page_count": len({b.page_no for b in text_blocks} | {i.page_no for i in images})},
    )


def _parse_docx(content: bytes) -> ParsedDocument:
    doc = Document(BytesIO(content))
    text_blocks: list[TextBlock] = []
    images: list[ImageAsset] = []
    nodes: list[ContentNode] = []
    order = 0
    image_index = 0
    recent_text = ""

    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, doc)
            text = paragraph.text.strip()
            if text:
                rendered = _render_docx_paragraph(paragraph, text)
                text_blocks.append(
                    TextBlock(text=rendered, page_no=None, order=order, kind="paragraph")
                )
                nodes.append(
                    ContentNode(
                        kind="markdown" if rendered != text else "text",
                        text=rendered,
                        page_no=None,
                        order=order,
                    )
                )
                order += 1
                recent_text = text
        elif child.tag.endswith("}tbl"):
            table_md = _render_docx_table(Table(child, doc))
            if table_md:
                text_blocks.append(TextBlock(table_md, None, order, kind="table"))
                nodes.append(ContentNode(kind="table", text=table_md, order=order))
                order += 1
                recent_text = table_md[:800]

        for relationship_id in child.xpath(".//a:blip/@r:embed"):
            part = doc.part.related_parts.get(relationship_id)
            image_bytes = getattr(part, "blob", None)
            if not image_bytes:
                continue
            content_type = str(getattr(part, "content_type", "image/png"))
            ext = Path(str(getattr(part, "partname", "image.png"))).suffix.lstrip(".")
            image = _make_image_asset(
                image_bytes,
                ext or _extension_from_mime(content_type),
                page_no=None,
                image_index=image_index,
                nearby_text=recent_text[:800],
                mime_type=content_type,
            )
            images.append(image)
            nodes.append(
                ContentNode(
                    kind="image", order=order, page_no=None, image_sha256=image.sha256
                )
            )
            order += 1
            image_index += 1

    return ParsedDocument(
        text_blocks=text_blocks,
        images=images,
        nodes=nodes,
        metadata={"file_type": "docx", "page_count": None},
    )


def _make_image_asset(
    content: bytes,
    extension: str,
    *,
    page_no: int | None,
    image_index: int,
    nearby_text: str = "",
    is_page_scan: bool = False,
    mime_type: str | None = None,
) -> ImageAsset:
    ext = (extension or "png").lower().lstrip(".")
    if ext == "jpeg":
        ext = "jpg"
    width: int | None = None
    height: int | None = None
    detected_mime = mime_type
    try:
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
            if not detected_mime:
                detected_mime = Image.MIME.get(image.format or "")
            detected_ext = (image.format or "").lower()
            if detected_ext:
                ext = "jpg" if detected_ext == "jpeg" else detected_ext
    except (UnidentifiedImageError, OSError):
        pass
    return ImageAsset(
        content=content,
        page_no=page_no,
        page_numbers=[page_no] if page_no is not None else [],
        image_index=image_index,
        width=width,
        height=height,
        mime_type=detected_mime or f"image/{'jpeg' if ext == 'jpg' else ext}",
        extension=ext,
        nearby_text=nearby_text,
        is_page_scan=is_page_scan,
    )


def _extension_from_mime(mime_type: str) -> str:
    subtype = mime_type.rsplit("/", 1)[-1].lower()
    return "jpg" if subtype == "jpeg" else subtype


def _render_docx_paragraph(paragraph: Paragraph, text: str) -> str:
    style = str(getattr(getattr(paragraph, "style", None), "name", "") or "")
    if style.lower().startswith("heading"):
        suffix = style.rsplit(" ", 1)[-1]
        level = int(suffix) if suffix.isdigit() else 1
        return f"{'#' * min(6, level + 1)} {text}"
    if "list bullet" in style.lower():
        return f"- {text}"
    if "list number" in style.lower():
        return f"1. {text}"
    return text


def _render_docx_table(table: Table) -> str:
    rows = [[cell.text.strip().replace("|", "\\|") for cell in row.cells] for row in table.rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = normalized[0]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in normalized[1:])
    return "\n".join(lines)
