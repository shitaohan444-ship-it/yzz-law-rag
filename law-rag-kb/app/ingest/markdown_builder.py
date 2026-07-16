"""统一 Markdown 构建、draft 切片、VL 回填与最终整形。"""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.ingest import chunker
from app.ingest.document import ImageAnalysis, ParsedDocument
from app.rag.markdown import extract_image_ids


_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$")
_ARTICLE_TITLE_RE = re.compile(r"^第[一二三四五六七八九十百千零〇两0-9]+条$")
_PART_TITLE_RE = re.compile(
    r"^第[一二三四五六七八九十百千零〇两0-9]+编(?:\s+.+)?$"
)
_CHAPTER_TITLE_RE = re.compile(
    r"^第[一二三四五六七八九十百千零〇两0-9]+章(?:\s+.+)?$"
)
_SECTION_TITLE_RE = re.compile(
    r"^第[一二三四五六七八九十百千零〇两0-9]+节(?:\s+.+)?$"
)
_PLAIN_ARTICLE_LINE_RE = re.compile(
    r"^[ \t]*(第[一二三四五六七八九十百千零〇两0-9]+条)"
    r"(?:[ \t\u3000]+(.*))?$"
)
_PLAIN_CHAPTER_LINE_RE = re.compile(
    r"^[ \t]*(第[一二三四五六七八九十百千零〇两0-9]+[章节编](?:[ \t]+.*)?)$"
)
_INITIAL_IMAGE_BLOCK_RE = re.compile(
    r"(?m)^### (?P<label>[^\n]*图片[^\n]*)\n"
    r"!\[(?P<alt>[^\]]*)\]\(#img:(?P<id>\d+)\)"
)


@dataclass(frozen=True)
class DraftChunk:
    idx: int
    text: str
    article_no: str | None = None
    chapter: str | None = None
    image_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class MarkdownChunk:
    idx: int
    text: str
    article_no: str | None = None
    chapter: str | None = None
    image_ids: tuple[int, ...] = ()


def build_initial_markdown(
    doc_title: str,
    document: ParsedDocument,
    image_ids: dict[str, int],
) -> str:
    """把解析结果转换为尚未经过 VL 的规范 Markdown。"""
    title = _clean_title(doc_title or "未命名文档")
    parts: list[str] = [f"# {title}"]
    body: list[str] = []
    referenced: set[str] = set()

    nodes = sorted(document.nodes, key=lambda node: node.order)
    if not nodes:
        # 兼容直接构造 ParsedDocument 的旧调用方和测试。
        if document.text:
            nodes_text = (
                document.text
                if document.metadata.get("file_type") == "md"
                else chunker.to_markdown(document.text)
            )
            if nodes_text:
                body.append(nodes_text)
        for image in document.images:
            image_id = image_ids.get(image.sha256)
            if image_id is not None:
                body.append(_initial_image_block(image.page_no, image_id))
                referenced.add(image.sha256)
    else:
        for node in nodes:
            if node.kind == "image":
                sha = node.image_sha256 or ""
                image_id = image_ids.get(sha)
                if image_id is not None:
                    body.append(_initial_image_block(node.page_no, image_id))
                    referenced.add(sha)
                continue
            text = (node.text or "").strip()
            if not text:
                continue
            if node.kind == "markdown":
                body.append(_promote_legal_lines(text))
            elif node.kind == "table":
                body.append(text)
            else:
                rendered = chunker.to_markdown(text)
                if rendered:
                    body.append(rendered)

        # content_text 覆盖或旧解析结果可能没有图片节点，统一追加到附图区。
        orphans = [
            image for image in document.images
            if image.sha256 not in referenced and image.sha256 in image_ids
        ]
        if orphans:
            body.append("## 附图")
            body.extend(
                _initial_image_block(image.page_no, image_ids[image.sha256])
                for image in orphans
            )

    if body:
        parts.append("## 正文")
        parts.extend(body)
    return _normalize("\n\n".join(parts))


def split_markdown_draft(
    markdown: str, *, chunk_size: int, overlap: int
) -> list[DraftChunk]:
    """第一次块级切片；输出给 VL 使用的稳定上下文。"""
    markdown = _normalize(markdown)
    if not markdown:
        return []
    blocks = _scan_blocks(markdown)
    if not blocks:
        return []

    title = "# 未命名文档"
    title_seen = False
    current_document_section: str | None = None
    current_part_heading: str | None = None
    current_chapter_heading: str | None = None
    current_chapter: str | None = None
    current_legal_section_heading: str | None = None
    current_article_heading: str | None = None
    current_article: str | None = None
    buffer: list[str] = []
    drafts: list[DraftChunk] = []

    def prefix() -> list[str]:
        values = [title]
        for value in (
            current_document_section,
            current_part_heading,
            current_chapter_heading,
            current_legal_section_heading,
            current_article_heading,
        ):
            if value and value not in values:
                values.append(value)
        return values

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        text = _normalize("\n\n".join(prefix() + buffer))
        drafts.append(
            DraftChunk(
                idx=len(drafts),
                text=text,
                article_no=current_article,
                chapter=current_chapter,
                image_ids=tuple(extract_image_ids(text)),
            )
        )
        buffer = []

    for block in blocks:
        heading = _heading(block)
        if heading:
            level, heading_text = heading
            if level == 1:
                flush()
                if not title_seen:
                    title = f"# {heading_text}"
                    title_seen = True
                else:
                    # 原生 MD 正文中的 H1 降为文档内 section，顶层文档标题保持稳定。
                    current_document_section = f"## {heading_text}"
                    current_part_heading = None
                    current_chapter_heading = None
                    current_chapter = None
                    current_legal_section_heading = None
                    current_article_heading = None
                    current_article = None
                continue
            rendered_heading = f"{'#' * level} {heading_text}"
            if _PART_TITLE_RE.match(heading_text):
                flush()
                current_part_heading = rendered_heading
                current_chapter_heading = None
                current_chapter = None
                current_legal_section_heading = None
                current_article_heading = None
                current_article = None
                continue
            if _CHAPTER_TITLE_RE.match(heading_text):
                flush()
                current_chapter_heading = rendered_heading
                current_chapter = heading_text
                current_legal_section_heading = None
                current_article_heading = None
                current_article = None
                continue
            if _SECTION_TITLE_RE.match(heading_text):
                flush()
                current_legal_section_heading = rendered_heading
                current_article_heading = None
                current_article = None
                continue
            if _ARTICLE_TITLE_RE.match(heading_text):
                flush()
                current_article_heading = rendered_heading
                current_article = heading_text
                continue
            if level == 2:
                flush()
                current_document_section = rendered_heading
                current_part_heading = None
                current_chapter_heading = None
                current_chapter = None
                current_legal_section_heading = None
                current_article_heading = None
                current_article = None
                continue

        block_has_image = bool(extract_image_ids(block))
        if block_has_image:
            # 图片是独立语义块，不能继承前一法条 metadata；VL 上下文由 image_contexts
            # 额外拼接相邻 draft，而不是把图片归到最后一条法条。
            flush()
            current_article_heading = None
            current_article = None
            buffer.append(block)
            flush()
            continue
        candidate = _normalize("\n\n".join(prefix() + buffer + [block]))
        if buffer and len(candidate) > chunk_size:
            flush()
        buffer.append(block)
        if len(_normalize("\n\n".join(prefix() + buffer))) >= chunk_size:
            flush()

    flush()
    return [DraftChunk(i, d.text, d.article_no, d.chapter, d.image_ids) for i, d in enumerate(drafts)]


def image_contexts(drafts: list[DraftChunk]) -> dict[int, str]:
    """返回 image_id → 第一次切片上下文；同图多处出现时取首个上下文。"""
    contexts: dict[int, str] = {}
    for index, draft in enumerate(drafts):
        for image_id in draft.image_ids:
            nearby = drafts[index - 1].text if index > 0 else ""
            context = _normalize("\n\n".join(value for value in (nearby, draft.text) if value))
            contexts.setdefault(image_id, context)
    return contexts


def enrich_markdown(
    markdown: str,
    analyses_by_id: dict[int, ImageAnalysis],
    *,
    description_summary: str | None = None,
) -> str:
    """删除无效图片并将保留图片的描述/OCR回填 Markdown。"""
    enriched = _replace_image_blocks(markdown, analyses_by_id)
    if description_summary and enriched:
        lines = enriched.splitlines()
        insert_at = 1 if lines and lines[0].startswith("# ") else 0
        summary = ["", "## 文档概述", "", description_summary.strip(), ""]
        lines[insert_at:insert_at] = summary
        enriched = "\n".join(lines)
    return _normalize(enriched)


def enrich_drafts(
    drafts: list[DraftChunk], analyses_by_id: dict[int, ImageAnalysis]
) -> list[DraftChunk]:
    result: list[DraftChunk] = []
    for draft in drafts:
        text = _replace_image_blocks(draft.text, analyses_by_id)
        # 图片失败/过滤后只剩重复标题时不形成无意义 chunk。
        if not _has_payload(text):
            continue
        result.append(
            DraftChunk(
                idx=len(result),
                text=text,
                article_no=draft.article_no,
                chapter=draft.chapter,
                image_ids=tuple(extract_image_ids(text)),
            )
        )
    return result


def finalize_chunks(
    drafts: list[DraftChunk],
    *,
    description_summary: str | None,
    doc_title: str,
    chunk_size: int,
    overlap: int,
) -> list[MarkdownChunk]:
    """加入独立概述块，并只对回填后超长 draft 做二次整形。"""
    chunks: list[MarkdownChunk] = []
    title = f"# {_clean_title(doc_title or '未命名文档')}"
    if description_summary:
        summary_text = _normalize(
            f"{title}\n\n## 文档概述\n\n{description_summary.strip()}"
        )
        chunks.extend(_split_one(summary_text, None, None, chunk_size, overlap))
    for draft in drafts:
        chunks.extend(
            _split_one(
                draft.text,
                draft.article_no,
                draft.chapter,
                chunk_size,
                overlap,
            )
        )
    return [
        MarkdownChunk(
            idx=i,
            text=item.text,
            article_no=item.article_no,
            chapter=item.chapter,
            image_ids=item.image_ids,
        )
        for i, item in enumerate(chunks)
    ]


def _split_one(
    text: str,
    article_no: str | None,
    chapter: str | None,
    chunk_size: int,
    overlap: int,
) -> list[MarkdownChunk]:
    text = _normalize(text)
    ids = tuple(extract_image_ids(text))
    if len(text) <= chunk_size:
        return [MarkdownChunk(0, text, article_no, chapter, ids)]

    prefix, payload = _split_prefix(text, include_image=bool(ids))
    budget = max(80, chunk_size - len(prefix) - 2)
    parts = chunker.split(payload, budget, min(overlap, max(0, budget // 3)), by_article=False)
    if not parts:
        parts = [chunker.Chunk(0, payload)]
    return [
        MarkdownChunk(
            idx=i,
            text=_normalize(f"{prefix}\n\n{part.text}"),
            article_no=article_no,
            chapter=chapter,
            image_ids=tuple(extract_image_ids(f"{prefix}\n{part.text}")),
        )
        for i, part in enumerate(parts)
    ]


def _split_prefix(text: str, *, include_image: bool) -> tuple[str, str]:
    blocks = _scan_blocks(text)
    prefix_blocks: list[str] = []
    payload_blocks: list[str] = []
    image_seen = False
    for block in blocks:
        is_heading = bool(_heading(block))
        has_image = bool(extract_image_ids(block))
        if is_heading and not payload_blocks:
            prefix_blocks.append(block)
            continue
        if include_image and has_image and not image_seen:
            prefix_blocks.append(block)
            image_seen = True
            continue
        payload_blocks.append(block)
    prefix = _normalize("\n\n".join(prefix_blocks))
    payload = _normalize("\n\n".join(payload_blocks))
    if not payload:
        # 极长原子块最后回退字符切分，但仍保持标题在每个片段中。
        payload = prefix_blocks.pop() if prefix_blocks else text
        prefix = _normalize("\n\n".join(prefix_blocks))
    return prefix, payload


def _replace_image_blocks(
    text: str, analyses_by_id: dict[int, ImageAnalysis]
) -> str:
    def replace(match: re.Match) -> str:
        image_id = int(match.group("id"))
        analysis = analyses_by_id.get(image_id)
        if not analysis or analysis.status != "success" or not analysis.keep_for_rag:
            return ""
        desc = (analysis.description or "").strip()
        ocr = (analysis.extracted_text or "").strip()
        alt_source = desc or ocr or "图片"
        alt = _sanitize_alt(alt_source[:40] + ("…" if len(alt_source) > 40 else ""))
        lines = [f"### {match.group('label')}", f"![{alt}](#img:{image_id})"]
        if desc:
            lines.append(f"**图片说明：** {desc}")
        if ocr:
            lines.append(f"**图片识别文字：** {ocr}")
        return "\n\n".join(lines)

    return _normalize(_INITIAL_IMAGE_BLOCK_RE.sub(replace, text or ""))


def _initial_image_block(page_no: int | None, image_id: int) -> str:
    label = f"第{page_no}页图片" if page_no else "文档图片"
    return f"### {label}\n![待识别图片](#img:{image_id})"


def _scan_blocks(markdown: str) -> list[str]:
    """按空行扫描 Markdown，同时保护 fenced code 内的空行。"""
    blocks: list[str] = []
    current: list[str] = []
    fence: str | None = None
    for line in (markdown or "").splitlines():
        stripped = line.lstrip()
        marker = stripped[:3] if stripped.startswith(("```", "~~~")) else None
        is_heading = bool(_HEADING_RE.match(line)) if fence is None else False
        if is_heading and current:
            blocks.append("\n".join(current).strip())
            current = []
        elif (
            current
            and _HEADING_RE.match(current[0])
            and not current[0].endswith("图片")
            and line.strip()
            and marker is None
        ):
            # Markdown 标题即使后面没有空行也应形成独立结构块。
            blocks.append("\n".join(current).strip())
            current = []
        if marker:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
        if not line.strip() and fence is None:
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def _heading(block: str) -> tuple[int, str] | None:
    first = block.splitlines()[0] if block else ""
    match = _HEADING_RE.match(first)
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def _has_payload(text: str) -> bool:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return any(not line.startswith("#") for line in lines)


def _sanitize_alt(text: str) -> str:
    return text.replace("[", "（").replace("]", "）").replace("\n", " ")


def _promote_legal_lines(markdown: str) -> str:
    """在不改动 Markdown 缩进/表格/代码块的前提下提升裸章、条标题。"""
    out: list[str] = []
    fence: str | None = None
    for line in (markdown or "").splitlines():
        stripped = line.lstrip()
        marker = stripped[:3] if stripped.startswith(("```", "~~~")) else None
        if marker:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            out.append(line)
            continue
        if fence is not None or stripped.startswith("#"):
            out.append(line)
            continue
        chapter = _PLAIN_CHAPTER_LINE_RE.match(line)
        if chapter:
            out.append(f"## {chapter.group(1).strip()}")
            continue
        article = _PLAIN_ARTICLE_LINE_RE.match(line)
        if article:
            out.append(f"### {article.group(1).strip()}")
            remainder = (article.group(2) or "").strip()
            if remainder:
                out.append(remainder)
            continue
        out.append(line)
    return "\n".join(out)


def _clean_title(text: str) -> str:
    return re.sub(r"[\r\n]+", " ", text or "").strip().lstrip("#").strip()


def _normalize(text: str) -> str:
    value = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    while "\n\n\n" in value:
        value = value.replace("\n\n\n", "\n\n")
    return value
