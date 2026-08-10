"""结构化文档解析：PDF / DOCX / TXT / Markdown / 常见图片。"""
import posixpath
import re
import zipfile
from io import BytesIO
from pathlib import Path

import fitz
from docx import Document
from docx.oxml.ns import qn
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


# 匹配 .rels 里的单个 <Relationship .../> 元素（自闭合或成对）。
_RELATIONSHIP_RE = re.compile(rb"<Relationship\b[^>]*?(?:/>|>.*?</Relationship>)", re.DOTALL)
# Target / TargetMode 属性值，单双引号都容忍。
_TARGET_ATTR_RE = re.compile(rb"""\bTarget\s*=\s*["']([^"']*)["']""")
_TARGETMODE_ATTR_RE = re.compile(rb"""\bTargetMode\s*=\s*["']([^"']*)["']""")


def _rels_base_dir(rels_part_name: str) -> str:
    """由 .rels 部件路径推出其描述的主件所在目录。

    例如 ``word/_rels/document.xml.rels`` -> ``word``，
    根级 ``_rels/.rels`` -> ``""``（包根）。
    """
    directory, _, filename = rels_part_name.rpartition("/")
    if filename == ".rels":  # 根级 _rels/.rels，描述整个包
        return ""
    # directory 形如 "word/_rels"，主件目录是去掉末尾 "_rels"
    parent = directory.rsplit("/", 1)[0] if "/" in directory else ""
    return parent


def _sanitize_docx(content: bytes) -> bytes:
    """剔除 .rels 中指向不存在部件的内部关系引用后重打包。

    部分工具（如 WPS）导出的 docx 会在关系表里保留指向
    ``userCustomization/customUI.xml`` 等并未实际打进包的部件引用，
    python-docx 严格校验会直接抛 ``KeyError`` 导致整篇解析失败。
    这里删掉这些"悬空"关系（外部链接 TargetMode="External" 保留），
    让 python-docx 能正常打开。无法识别为标准 zip/docx 时原样返回。
    """
    try:
        source = zipfile.ZipFile(BytesIO(content))
        names = set(source.namelist())
    except zipfile.BadZipFile:
        return content

    rewritten: dict[str, bytes] = {}
    changed = False
    for name in names:
        if not name.endswith(".rels"):
            continue
        data = source.read(name)
        base_dir = _rels_base_dir(name)

        def _drop_dangling(match: "re.Match[bytes]") -> bytes:
            nonlocal changed
            element = match.group(0)
            target_mode = _TARGETMODE_ATTR_RE.search(element)
            if target_mode and target_mode.group(1).decode("utf-8", "replace").lower() == "external":
                return element  # 外部链接不校验包内是否存在
            target = _TARGET_ATTR_RE.search(element)
            if not target:
                return element
            target_path = target.group(1).decode("utf-8", "replace")
            if target_path.startswith("/"):
                part = target_path.lstrip("/")
            else:
                part = posixpath.normpath(posixpath.join(base_dir, target_path)) if base_dir else posixpath.normpath(target_path)
            if part not in names:
                changed = True
                return b""  # 部件缺失，剔除该关系引用
            return element

        new_data = _RELATIONSHIP_RE.sub(_drop_dangling, data)
        if new_data != data:
            rewritten[name] = new_data

    if not changed:
        return content

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target_zip:
        for name in source.namelist():
            target_zip.writestr(name, rewritten.get(name) or source.read(name))
    return buffer.getvalue()


def _parse_docx(content: bytes) -> ParsedDocument:
    try:
        doc = Document(BytesIO(content))
    except Exception:
        # 关系表引用残缺（如 userCustomization/customUI.xml 未入包）时，
        # 清洗后重试一次；仍失败则原样抛出，交由上层标记 FAILED。
        doc = Document(BytesIO(_sanitize_docx(content)))
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

        # 用 Clark 记法而非带前缀的 xpath：body 里未在 python-docx 注册的元素
        # （如 w:bookmarkEnd/w:sdt）是裸 lxml 元素，前缀 xpath 会因缺少
        # 命名空间映射抛 XPathEvalError，导致整篇入库失败。
        for blip in child.iter(qn("a:blip")):
            relationship_id = blip.get(qn("r:embed"))
            if not relationship_id:
                continue
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
