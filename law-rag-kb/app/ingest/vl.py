"""阿里云百炼 Qwen VL 图片分类与描述客户端。"""
from __future__ import annotations

import base64
import json
import logging

from app.core.config import settings
from app.ingest.document import ImageAnalysis, ImageAsset

logger = logging.getLogger(__name__)


class VisionClientError(RuntimeError):
    """对上层隐藏密钥、图片内容和供应商响应的稳定错误。"""


class _PayloadParseError(ValueError):
    """解析失败时携带脱敏诊断元数据，供上层拼装稳定错误信息。"""

    def __init__(self, meta: dict, cause: Exception):
        super().__init__(str(cause))
        self.meta = meta
        self.cause = cause


_CATEGORIES = {
    "decorative_logo",
    "watermark",
    "separator",
    "stamp_seal",
    "signature",
    "qr_barcode",
    "table",
    "diagram",
    "screenshot",
    "evidence_photo",
    "page_scan",
    "other",
}
_FILTERABLE = {"decorative_logo", "watermark", "separator"}
_IMPORTANT = {
    "stamp_seal",
    "signature",
    "qr_barcode",
    "table",
    "diagram",
    "screenshot",
    "evidence_photo",
    "page_scan",
}

# qwen3-vl-plus 非确定输出：偶尔用 Unicode 引号（“ ”‘ ’« »＂ 等）包裹键/值替代 ASCII 双引号，
# 标准 json.loads 只认 U+0022，于是报 "Expecting property name enclosed in double quotes"。
# 下面把开引号映射到它可接受的闭引号集合，用于结构感知地归一化（仅替换分隔符，保留正文里的弯引号）。
_QUOTE_CLOSERS: dict[str, tuple[str, ...]] = {
    '"': ('"',),
    "“": ("”", "“"),  # “ 开，” 闭
    "”": ("”",),
    "„": ("‟", "„"),  # „ ‟
    "'": ("'",),
    "‘": ("’", "‘"),  # ‘ ’
    "’": ("’",),
    "«": ("»",),           # « »
    "»": ("»",),
    "＂": ("＂",),           # ＂ 全角双引号
}
_QUOTE_OPENERS = frozenset(_QUOTE_CLOSERS)


def analyze(
    image: ImageAsset, *, doc_title: str, context_text: str | None = None
) -> ImageAnalysis:
    """调用 VL；非法 JSON 会再请求一次格式修复。"""
    if not settings.vl_configured:
        raise VisionClientError("VL is enabled but not configured")
    prompt = _build_prompt(image, doc_title=doc_title, context_text=context_text)
    last_meta: dict | None = None
    last_error: Exception | None = None
    for attempt in range(2):
        suffix = (
            "\n上次输出无法解析，请只返回一个JSON对象，不要附带任何说明文字或Markdown代码块。"
            if attempt
            else ""
        )
        try:
            content, prompt_tokens, completion_tokens, finish_reason = _request(
                image, prompt + suffix
            )
            payload, meta = _parse_payload(content, finish_reason=finish_reason)
            return _build_analysis(image, payload, prompt_tokens, completion_tokens)
        except _PayloadParseError as exc:
            last_meta = exc.meta
            last_error = exc.cause
            continue
        except Exception as exc:
            raise VisionClientError(
                f"VL provider request failed ({type(exc).__name__})"
            ) from exc

    message = _format_failure(last_meta, last_error)
    # 只记录脱敏元数据（响应类型/长度/finish_reason/是否截断），不含图片、Key 或正文。
    logger.warning("VL JSON parse failed: %s", message)
    raise VisionClientError(message)


def failed_analysis(image: ImageAsset, error: Exception) -> ImageAnalysis:
    return ImageAnalysis(
        asset=image,
        status="failed",
        category="page_scan" if image.is_page_scan else None,
        keep_for_rag=False,
        error_message=str(error)[:500],
    )


def _request(image: ImageAsset, prompt: str):
    """返回 (content, prompt_tokens, completion_tokens, finish_reason)。"""
    from openai import OpenAI

    client = OpenAI(
        base_url=settings.vl_api_base,
        api_key=settings.vl_effective_api_key,
        timeout=settings.vl_timeout_seconds,
        max_retries=settings.vl_max_retries,
    )
    encoded = base64.b64encode(image.content).decode("ascii")
    response = client.chat.completions.create(
        model=settings.vl_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image.mime_type};base64,{encoded}"
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        temperature=0,
        max_tokens=settings.vl_max_output_tokens,
        extra_body={"enable_thinking": False},
    )
    # qwen3-vl-plus 经百炼 OpenAI 兼容模式返回 message.content 为字符串；
    # 这里对 list/None 一并兜底，避免个别版本返回内容块数组时整体崩掉。
    message = response.choices[0].message
    content = getattr(message, "content", None)
    finish_reason = getattr(response.choices[0], "finish_reason", None)
    usage = getattr(response, "usage", None)
    return (
        content,
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
        finish_reason,
    )


def _build_prompt(
    image: ImageAsset, *, doc_title: str, context_text: str | None = None
) -> str:
    nearby = (context_text if context_text is not None else image.nearby_text)[
        : settings.vl_nearby_text_chars
    ]
    page = image.page_no if image.page_no is not None else "未知"
    repeated = (
        f"同一图片出现在页码：{image.page_numbers}，可能是重复页眉、Logo或水印。"
        if len(image.page_numbers) > 1
        else ""
    )
    scan_instruction = (
        "这是扫描页，请完整提取可读文字并概括页面内容。"
        if image.is_page_scan
        else "描述其中对法律检索有用的事实、表格、图示或文字。"
    )
    return f"""你是法律文档图片分析器。文档标题：{doc_title[:255]}；页码：{page}。
附近正文（可能为空）：{nearby}
{repeated}
{scan_instruction}
请判断图片类型。仅高置信度的装饰Logo、水印、分隔线可建议过滤；印章、签名、二维码、表格、流程图、截图、证据照片和扫描正文必须保留。
只返回一个JSON对象，不要Markdown：
{{"category":"decorative_logo|watermark|separator|stamp_seal|signature|qr_barcode|table|diagram|screenshot|evidence_photo|page_scan|other","keep_for_rag":true,"confidence":0.0,"description":"中文描述","extracted_text":"识别文字","filter_reason":"原因"}}"""


# --------------------------------------------------------------------------- #
# JSON 解析：规整 content → 花括号配平抽取 → 安全修复 → 字段校验
# --------------------------------------------------------------------------- #


def _parse_payload(content, *, finish_reason) -> tuple[dict, dict]:
    """解析模型响应为 dict；失败抛 _PayloadParseError 并携带脱敏诊断。"""
    text = _normalize_content(content)
    meta: dict = {
        "resp_type": type(content).__name__,
        "resp_len": len(text),
        "finish_reason": finish_reason,
        "balanced": None,
        "repaired": None,
        "reason": None,
    }
    if not text.strip():
        meta["reason"] = "empty_response"
        raise _PayloadParseError(meta, ValueError("empty response"))

    candidate, balanced = _extract_json_object(text)
    meta["balanced"] = balanced
    if not candidate:
        meta["reason"] = "json_object_not_found"
        raise _PayloadParseError(meta, ValueError("JSON object not found"))

    payload = _try_loads(candidate)
    if payload is None:
        # 安全修复：Unicode 弯引号分隔符归一化、字符串内裸控制字符转义、尾逗号删除。
        repaired = _normalize_json_text(candidate)
        payload = _try_loads(repaired)
        meta["repaired"] = payload is not None
    if payload is None:
        meta["reason"] = "json_decode_failed"
        try:
            json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise _PayloadParseError(meta, exc)
        raise _PayloadParseError(meta, ValueError("json decode failed"))

    if not isinstance(payload, dict):
        meta["reason"] = "not_object"
        raise _PayloadParseError(meta, ValueError("JSON response must be an object"))

    meta["reason"] = "ok"
    return payload, meta


def _normalize_content(content) -> str:
    """content 可能是 str / list[str|dict] / None；统一成 str。

    qwen3-vl-plus 正常返回 str；list 分支用于兜底个别返回内容块数组的版本，
    或上游 SDK 升级后 message.content 变为 OpenAI 内容块列表的情形。
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content)


def _extract_json_object(text: str) -> tuple[str, bool]:
    """从任意包装中抽取第一个完整 JSON 对象。

    用花括号配平（跳过字符串内的括号）替代 find/rfind，避免 JSON 前后说明文字
    里混入的 {/} 导致首尾错配。返回 (子串, 是否配平)；未配平视为疑似截断。
    """
    start = text.find("{")
    if start < 0:
        return "", False
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1], True
    # 走到末尾仍未配平 → 把首个 { 之后的内容全部返回，供上层判断截断。
    return text[start:], False


def _normalize_json_text(raw: str) -> str:
    """对模型返回的 JSON 做保守、结构感知的安全修复，单次行走完成：

    - **Unicode 引号归一化**：把 “ ”‘ ’« »＂ 等 Unicode 引号 *分隔符* 替换为 ASCII
      U+0022。用“开引号 → 其可接受的闭引号集合”配对识别字符串边界，字符串 *正文*
      里的弯引号（与开引号不同类）原样保留，不会被误伤。这是 qwen3-vl-plus 描述
      流程图/表格时偶发的 "Expecting property name enclosed in double quotes"
      的根因修复。
    - **裸控制字符转义**：字符串值内的换行/回车/制表等 (<0x20) 转义为 \\n/\\r/\\t/\\uXXXX。
    - **尾逗号删除**：} / ] 前的逗号丢弃。

    非 ASCII 引号在串内作正文时不会被当成分隔符，故对合法 ASCII JSON 输入近乎等价。
    """
    out: list[str] = []
    i = 0
    n = len(raw)
    in_str = False
    closers: tuple[str, ...] = ()
    escape = False
    while i < n:
        ch = raw[i]
        if in_str:
            if escape:
                out.append(ch)
                escape = False
            elif ch == "\\":
                out.append(ch)
                escape = True
            elif ch in closers:
                # 配对的闭引号 → 用 ASCII " 收尾。
                out.append('"')
                in_str = False
                closers = ()
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            elif ch == "\t":
                out.append("\\t")
            elif ord(ch) < 0x20:
                out.append(f"\\u{ord(ch):04x}")
            else:
                # 正文：包括与开引号不同类的 Unicode 引号，原样保留。
                out.append(ch)
        else:
            if ch in _QUOTE_OPENERS:
                out.append('"')
                in_str = True
                closers = _QUOTE_CLOSERS[ch]
            elif ch == ",":
                # 向前看：下一个非空白字符是 } 或 ] 则丢弃该尾逗号。
                j = i + 1
                while j < n and raw[j].isspace():
                    j += 1
                if j < n and raw[j] in "}]":
                    pass
                else:
                    out.append(ch)
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def _try_loads(candidate: str):
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None


def _format_failure(meta: dict | None, error: Exception | None) -> str:
    """组装脱敏错误信息：只含响应类型/长度/finish_reason/是否截断/原因。"""
    if not meta:
        kind = type(error).__name__ if error else "unknown"
        return f"VL returned invalid JSON ({kind})"
    truncated = bool(meta.get("finish_reason") == "length") or meta.get(
        "balanced", True
    ) is False
    kind = type(error).__name__ if error else "unknown"
    return (
        f"VL returned invalid JSON "
        f"(resp_type={meta.get('resp_type')}, resp_len={meta.get('resp_len')}, "
        f"finish_reason={meta.get('finish_reason')}, truncated={truncated}, "
        f"reason={meta.get('reason')}, error={kind})"
    )


def _build_analysis(
    image: ImageAsset, payload: dict, prompt_tokens, completion_tokens
) -> ImageAnalysis:
    """字段校验与类型规整，再套用法律安全保留策略。"""
    category = str(payload.get("category") or "other").strip() or "other"
    if category not in _CATEGORIES:
        category = "other"
    confidence = _clamp_confidence(payload.get("confidence"))
    if category in _IMPORTANT:
        keep = True
    elif category in _FILTERABLE:
        keep = confidence < settings.vl_filter_confidence
    else:
        keep = _coerce_bool(payload.get("keep_for_rag"), True)
    if not keep and category not in _FILTERABLE:
        keep = True
    return ImageAnalysis(
        asset=image,
        status="success",
        category=category,
        keep_for_rag=keep,
        filter_reason=(str(payload.get("filter_reason") or "")[:500] or None),
        confidence=confidence,
        description=str(payload.get("description") or "").strip(),
        extracted_text=str(payload.get("extracted_text") or "").strip(),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def _clamp_confidence(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _coerce_bool(value, default: bool = False) -> bool:
    """容忍模型把布尔写成 "true"/"false"/1/0。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"true", "1", "yes", "y"}:
            return True
        if token in {"false", "0", "no", "n"}:
            return False
    return default
