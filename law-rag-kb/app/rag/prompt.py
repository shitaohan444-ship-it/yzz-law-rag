"""法律域 RAG prompt 组装 + 引用（knowledge_refs）结构。

片段行格式固定为 [n] 《title》— 文本，stub LLM 与真实 LLM 共用同一 prompt；
build_prompt 因 max_chars 截断时返回实际入 prompt 的 hits 子集，保证与 build_refs 编号对齐。
"""
from app.rag.retrieve import SearchHit
from app.rag.markdown import strip_for_llm

_SYSTEM = (
    "你是一名中国法律助理。请严格基于下方【检索到的法律依据】回答【用户问题】，"
    "并在引用某条依据处用 [n] 标注（n 对应依据编号）。若依据不足以回答，请直接说明，"
    "切勿编造法条或案例。回答用中文。"
)


def build_prompt(
    question: str, hits: list[SearchHit], *, max_chars: int
) -> tuple[str, list[SearchHit]]:
    """组装 prompt，返回 (prompt 文本, 实际入 prompt 的 hits 子集)。

    片段按顺序编号 [n]，累计字符达 max_chars 后停止（防爆 token）；编号与返回子集一致。
    """
    lines = [_SYSTEM, "", "【检索到的法律依据】"]
    used: list[SearchHit] = []
    total = 0
    for i, h in enumerate(hits, 1):
        remaining = max_chars - total
        if remaining <= 20:
            break
        title = h.doc_title or "未命名文档"
        label = f"《{title}》{h.article_no}" if h.article_no else f"《{title}》"
        body = strip_for_llm(h.text).replace("\n", " ").strip()
        if len(body) > remaining:
            body = body[:remaining] + "…"
        total += len(body)
        lines.append(f"[{i}] {label} — {body}")
        used.append(h)

    lines += ["", f"【用户问题】{question}"]
    return "\n".join(lines), used


def build_refs(hits: list[SearchHit]) -> list[dict]:
    """组装 knowledge_refs（写 ai_chat_log）：编号与 build_prompt 返回子集对齐。"""
    return [
        {
            "ref_id": i,
            "chunk_id": h.chunk_id,
            "doc_id": h.doc_id,
            "doc_title": h.doc_title,
            "chunk_idx": h.chunk_idx,
            "source": h.source,
            "score": round(h.score, 4),
            "article_no": h.article_no,
            "chapter": h.chapter,
            "content_type": h.content_type,
            "image_id": h.image_id,
            "page_no": h.page_no,
            "image_category": h.image_category,
            "text": h.text,
        }
        for i, h in enumerate(hits, 1)
    ]
