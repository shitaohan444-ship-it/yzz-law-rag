"""文档级中文摘要生成（入库时调用，供 Markdown 渲染端点展示）。

复用 llm.get_llm().generate(...)；任何异常返回 None，不阻断入库（与 VL 失败同样的降级原则）。
"""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def generate_description(
    *,
    doc_title: str,
    body_text: str,
    image_summaries: list[str] | None = None,
) -> str | None:
    """基于标题 + 截断正文 + 各保留图片描述，生成一段文档级中文摘要。

    Returns:
        摘要文本；LLM 不可用或返回空时返回 None（调用方落库 NULL）。
    """
    from app.rag.llm import get_llm

    body = (body_text or "").strip()
    if not body and not (image_summaries or []):
        return None

    preview = body[: settings.kb_description_max_chars]
    img_block = ""
    if image_summaries:
        img_items = "\n".join(f"- {s}" for s in image_summaries if s)
        if img_items:
            img_block = f"\n\n文档包含以下图片：\n{img_items}"

    prompt = (
        "你是法律文档摘要助手。请基于下面的文档标题、正文片段和图片描述，"
        "用中文写一段 150~300 字的文档概述：说明这是什么文档、核心内容、"
        "涉及的要点或条款主题。只输出概述正文，不要标题、不要列表、不要复述原文。\n\n"
        f"文档标题：{doc_title or '（未命名）'}\n\n"
        f"正文片段：\n{preview}{img_block}"
    )

    try:
        text = get_llm().generate(prompt)
    except Exception as exc:  # LLMServiceError 或供应商异常一律降级
        logger.warning("document description generation failed (%s)", type(exc).__name__)
        return None
    text = (text or "").strip()
    return text or None
