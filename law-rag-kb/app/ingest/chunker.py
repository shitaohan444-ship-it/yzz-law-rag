"""法律文档切片器：条款级优先（阶段6）+ 中文标点递归回退。

条款级（chunk_by_article=True，默认）：识别"第X条"边界，一条法条至少生成一个
独立 chunk，并携带 {article_no, chapter} metadata；单条超长时递归拆成多个子块，
每个子块仍保留同一条款号。无条款结构的文档（判决书/起诉状/实务笔记）直接走
递归切分。chunk_idx 从 0 递增（参与 Milvus PK，必须稳定）。

阶段 2 按字符数计长（中文友好）；token 精确切分留后续。
"""
import re
from dataclasses import dataclass

# 递归分隔符层级：段落 → 换行 → 中文句末标点 → 分句标点 → 空格 → 字符
_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]

# 条款号/章节号用数字（中文 + 阿拉伯）
_NUM = r"一二三四五六七八九十百千零〇两0-9"
# 条文：行首（允许前导空白）的"第X条"，条号后须有横向空白或到达行尾。
# 这样既排除判决书正文中"《法典》第X条"，也避免把笔记里的"第一百条规定……"
# 误识别成结构化法规条文。支持普通空格、Tab 与中文全角空格。
_ARTICLE_RE = re.compile(rf"(?m)^[ \t#]*(第[{_NUM}]+条)(?=[ \t\u3000]|$)")
# chapter metadata 只允许“第X章”；“编”和“节”属于展示层级，不能覆盖所属章。
_CHAPTER_RE = re.compile(rf"(?m)^[ \t#]*(第[{_NUM}]+章[ \t]+[^\n]+)")
# Markdown 转换仍保留“编→章→节”的全部法律层级标题。
_LEGAL_HEADING_RE = re.compile(
    rf"(?m)^[ \t#]*(第[{_NUM}]+[编章节][ \t]+[^\n]+)"
)


@dataclass
class Chunk:
    idx: int
    text: str
    article_no: str | None = None  # "第十九条"；递归切片时为 None
    chapter: str | None = None  # "第二章 劳动合同的订立"


def split(
    text: str, chunk_size: int, overlap: int, *, by_article: bool = True
) -> list[Chunk]:
    """切分为若干 chunk。

    by_article=True 且文本具备条款结构（≥2 个"第X条"）时按条切并带 metadata；
    否则走字符递归（无 metadata，兼容判决书/起诉状等非条文文档）。
    """
    text = (text or "").strip()
    if not text:
        return []
    if by_article and _has_article_structure(text):
        return _split_by_article(text, chunk_size, overlap)
    return _split_recursive_wrap(text, chunk_size, overlap)


def to_markdown(text: str) -> str:
    """把纯文本正文轻量结构化为 Markdown，供渲染端点使用。

    复用条文/章节识别：行首“第X章/节/编 标题”→ `##`，行首“第X条”→ `###`；
    已经是 ``#`` 开头的行（.md 源或既有标题）原样保留，不重复加级。其余按段落输出。
    逐行处理，避免改动字符串字面内容。
    """
    text = (text or "").strip()
    if not text:
        return ""
    out: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.lstrip()
        if not stripped:
            if out and out[-1] != "":
                out.append("")  # 段落分隔
            continue
        # 已是 Markdown 标题（# 开头）原样保留
        if stripped.startswith("#"):
            out.append(stripped)
            continue
        m_legal_heading = _LEGAL_HEADING_RE.match(line)
        if m_legal_heading:
            out.append(f"## {m_legal_heading.group(1).strip()}")
            continue
        m_article = _ARTICLE_RE.match(line)
        if m_article:
            out.append(f"### {m_article.group(1).strip()}")
            # 条号同行可能带正文（"第十九条 劳动合同应当..."），保留条号之后的同行内容
            remainder = line[m_article.end():].strip()
            if remainder:
                out.append(remainder)
            continue
        out.append(stripped)
    # 去掉首尾空行、压缩 3+ 连续空行为 1 个
    result = "\n".join(out).strip()
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")
    return result


# ---------- 条款级切片 ----------


def _has_article_structure(text: str) -> bool:
    """至少 3 个正式条文边界才视为结构化法规，避免笔记/判决书偶发误判。"""
    return len(_ARTICLE_RE.findall(text)) >= 3


def _split_by_article(text: str, chunk_size: int, overlap: int) -> list[Chunk]:
    # 1. 章节标题位置（给每条标注所属章）
    chapters = [(m.start(), m.group(1).strip()) for m in _CHAPTER_RE.finditer(text)]
    # 2. 条款边界（行首"第X条"）
    arts = list(_ARTICLE_RE.finditer(text))
    # 3. 按条切段，每段带 article_no + 所属 chapter；第一条前的引言单独成段
    pieces: list[tuple[str | None, str | None, str]] = []
    if arts[0].start() > 0:
        intro = text[: arts[0].start()].strip()
        if intro:
            pieces.append((None, _chapter_at(chapters, 0), intro))
    for i, m in enumerate(arts):
        start = m.start()
        end = arts[i + 1].start() if i + 1 < len(arts) else len(text)
        ptext = text[start:end].strip()
        if ptext:
            pieces.append((m.group(1), _chapter_at(chapters, start), ptext))
    # 4. 每条法条独立成块；禁止合并相邻法条，否则一个 chunk 只能保存首条条款号，
    #    会造成正文召回正确但引用条款号错误。超长条递归拆分并继承同一条 meta。
    return _emit_article_pieces(pieces, chunk_size, overlap)


def _chapter_at(chapters: list[tuple[int, str]], pos: int) -> str | None:
    """返回位置 pos 之前最近的章节标题。"""
    ch = None
    for cpos, ctitle in chapters:
        if cpos <= pos:
            ch = ctitle
        else:
            break
    return ch


def _emit_article_pieces(
    pieces: list[tuple[str | None, str | None, str]], chunk_size: int, overlap: int
) -> list[Chunk]:
    """把结构化条文输出为 chunk，始终保持一个 chunk 只对应一个法条。

    第一条之前的标题/导言没有 article_no，可按普通文本递归拆分；每个法条正文即使
    很短也单独输出。超长法条拆分后的所有子块继承同一个 article_no/chapter。
    """
    chunks: list[Chunk] = []
    idx = 0
    for article_no, chapter, ptext in pieces:
        subtexts = (
            [ptext]
            if len(ptext) <= chunk_size
            else _recursive_split(ptext, _SEPARATORS, chunk_size, overlap)
        )
        for sub in subtexts:
            sub = sub.strip()
            if not sub:
                continue
            chunks.append(Chunk(idx, sub, article_no, chapter))
            idx += 1
    return chunks


# ---------- 字符递归切片（回退 + 无结构文档）----------


def _split_recursive_wrap(text: str, chunk_size: int, overlap: int) -> list[Chunk]:
    """无 metadata 的递归切片（原阶段2 逻辑，兼容非条文文档）。"""
    if len(text) <= chunk_size:
        return [Chunk(0, text)]
    pieces = _recursive_split(text, _SEPARATORS, chunk_size, overlap)
    chunks_text: list[str] = []
    buf = ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if not buf:
            buf = piece
        elif len(buf) + len(piece) + 1 <= chunk_size:
            buf += "\n" + piece
        else:
            chunks_text.append(buf)
            buf = piece
    if buf:
        chunks_text.append(buf)
    return [Chunk(i, t) for i, t in enumerate(chunks_text)]


def _recursive_split(
    text: str, separators: list[str], chunk_size: int, overlap: int
) -> list[str]:
    """递归按分隔符层级切分，直到每段 <= chunk_size 或用尽分隔符。"""
    if len(text) <= chunk_size:
        return [text]
    if not separators:
        step = max(1, chunk_size - overlap)
        return [text[i : i + chunk_size] for i in range(0, len(text), step)]

    sep = separators[0]
    rest = separators[1:]
    result: list[str] = []
    for part in text.split(sep):
        if len(part) <= chunk_size:
            result.append(part)
        else:
            result.extend(_recursive_split(part, rest, chunk_size, overlap))
    return result
