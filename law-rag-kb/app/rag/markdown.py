"""Markdown 图片占位符工具（统一切片流水线）。

Milvus 里存的 chunk_text 用稳定占位符 `![alt](#img:{image_id})` 引用图片——
预签名 URL 会过期、且 URL 串会污染向量，所以不能存进 Milvus。读路径
（/search、/chat）返回前现场把占位换成预签名 URL；喂给 LLM 的 prompt 则剥离成纯文本。
"""
from __future__ import annotations

import re

# 图片占位：![alt](#img:123)。group(1)=alt 文本，group(2)=image_id。
IMAGE_REF_RE = re.compile(r"!\[([^\]]*)\]\(#img:(\d+)\)")
_ANY_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def extract_image_ids(text: str) -> list[int]:
    """返回文本里出现的所有 image_id（去重保序）。"""
    seen: set[int] = set()
    ids: list[int] = []
    for m in IMAGE_REF_RE.finditer(text or ""):
        image_id = int(m.group(2))
        if image_id not in seen:
            seen.add(image_id)
            ids.append(image_id)
    return ids


def resolve_image_refs(text: str, id_to_url: dict[int, str]) -> str:
    """把 `![alt](#img:8)` 的链接换成 id_to_url[8]；未命中则降级为纯 alt 文本。

    降级（而非保留占位/抛错）保证前端拿到可读文本，不因单张图预签名失败整篇崩。
    """
    def _sub(m: re.Match) -> str:
        alt = m.group(1)
        image_id = int(m.group(2))
        url = id_to_url.get(image_id)
        return f"![{alt}]({url})" if url else (alt or "")

    return IMAGE_REF_RE.sub(_sub, text or "")


def strip_for_llm(text: str) -> str:
    """把 MD chunk 剥离成适合喂给 LLM 的纯文本。

    - 图片链接 → alt 文本（丢掉 URL，避免 URL 噪声进 prompt）；
    - 行首标题标记 `#`/`##`/`###`… 去掉；
    - 其余 MD 行内语法（**、`）保守保留，不明显影响理解。
    """
    if not text:
        return ""
    no_images = _ANY_IMAGE_RE.sub(lambda m: m.group(1), text)
    no_links = _LINK_RE.sub(lambda m: m.group(1), no_images)
    stripped = re.sub(r"(?m)^[ \t]{0,3}#{1,6}[ \t]*", "", no_links)
    stripped = re.sub(r"(?m)^[ \t]*>[ \t]?", "", stripped)
    stripped = re.sub(r"(?m)^[ \t]*(?:[-+*]|\d+[.)])[ \t]+", "", stripped)
    stripped = re.sub(r"(?m)^[ \t]*(?:```|~~~).*$", "", stripped)
    stripped = re.sub(r"[*_`~]{1,3}", "", stripped)
    stripped = re.sub(r"https?://\S+", "", stripped)
    return stripped.strip()
