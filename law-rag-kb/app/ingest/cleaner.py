"""结构化文档的文本清洗，保留页码与图片锚点。"""
from collections import Counter
from dataclasses import replace
import re
import unicodedata

from app.ingest.document import ContentNode, ParsedDocument, TextBlock


_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HORIZONTAL_SPACE_RE = re.compile(r"[ \t\u3000]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def clean(document: ParsedDocument) -> ParsedDocument:
    """归一化文本，并删除至少三页重复的短页眉/页脚。"""
    if document.metadata.get("file_type") == "md":
        # Markdown 的缩进、表格和代码块本身有语义，只统一换行，不做空白压缩。
        blocks = [replace(block, text=(block.text or "").replace("\r\n", "\n").replace("\r", "\n")) for block in document.text_blocks]
        nodes = [
            replace(node, text=(node.text or "").replace("\r\n", "\n").replace("\r", "\n"))
            if node.kind != "image" else node
            for node in document.nodes
        ]
        return replace(document, text_blocks=blocks, nodes=nodes)
    normalized = [replace(block, text=_normalize(block.text)) for block in document.text_blocks]
    repeated_edges = _find_repeated_page_edges(normalized)
    cleaned: list[TextBlock] = []
    for block in normalized:
        lines = [line for line in block.text.splitlines() if line.strip() not in repeated_edges]
        text = "\n".join(lines).strip()
        if text:
            cleaned.append(replace(block, text=text))
    cleaned_nodes: list[ContentNode] = []
    for node in document.nodes:
        if node.kind == "image":
            cleaned_nodes.append(node)
            continue
        text = _normalize(node.text)
        lines = [line for line in text.splitlines() if line.strip() not in repeated_edges]
        text = "\n".join(lines).strip()
        if text:
            cleaned_nodes.append(replace(node, text=text))
    return replace(document, text_blocks=cleaned, nodes=cleaned_nodes)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = _CONTROL_RE.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [_HORIZONTAL_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANK_LINES_RE.sub("\n\n", "\n".join(lines)).strip()


def _find_repeated_page_edges(blocks: list[TextBlock]) -> set[str]:
    pages: dict[int, list[str]] = {}
    for block in blocks:
        if block.page_no is not None:
            pages.setdefault(block.page_no, []).extend(
                line.strip() for line in block.text.splitlines() if line.strip()
            )
    candidates: Counter[str] = Counter()
    for lines in pages.values():
        if not lines:
            continue
        for line in {lines[0], lines[-1]}:
            if len(line) <= 120:
                candidates[line] += 1
    return {line for line, count in candidates.items() if count >= 3}
