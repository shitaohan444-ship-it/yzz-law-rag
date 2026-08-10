"""LLM 生成抽象层（provider 工厂）。

provider=stub（默认）：从 prompt 的结构化片段块拼模板答案，让 /chat 链路在无 key 时可验证。
provider=openai：OpenAI 兼容 API（DeepSeek / 智谱 / 通义 / OpenAI）。
provider=ollama：本地 Ollama（复用 OpenAI 兼容端点）。
切换只改 .env 的 LLM_PROVIDER + 凭据，业务代码（chat 编排）不动。

所有 provider 统一接口 generate(prompt: str) -> str；片段块格式见 prompt.build_prompt
（【检索到的法律依据】下 [n] 《title》— 文本 行，【用户问题】下问句），stub 依赖该格式提取。
"""
import re

from app.core.config import settings


class LLMServiceError(RuntimeError):
    """外部 LLM 不可用或返回无效结果；对 API 层隐藏密钥和底层请求细节。"""


def get_llm():
    """按 settings.llm_provider 返回对应实现（无状态，每次构造）。"""
    provider = settings.llm_provider.lower()
    if provider == "stub":
        return _StubLLM()
    if provider == "openai":
        return _OpenAILLM()
    if provider == "ollama":
        return _OllamaLLM()
    raise LLMServiceError(f"unknown llm_provider: {settings.llm_provider}")


class _StubLLM:
    """Mock 生成器：从 prompt 的结构化片段块拼模板答案，不调任何外部服务。

    仅用于链路验证；prompt 片段行格式由 prompt.build_prompt 固定。
    """

    _REF_RE = re.compile(r"^\[(\d+)\]\s+(.*)$")

    def generate(self, prompt: str, *, max_tokens: int | None = None) -> str:
        refs: list[tuple[str, str]] = []
        question = ""
        for line in prompt.splitlines():
            s = line.strip()
            if s.startswith("【用户问题】"):
                question = s.replace("【用户问题】", "").strip()
                continue
            m = self._REF_RE.match(s)
            if m:
                refs.append((m.group(1), m.group(2).strip()))

        if not refs:
            return (
                "[Stub 模式·未接真实 LLM] 未检索到相关法律依据，无法生成回答。"
                "接入真实 LLM（LLM_PROVIDER=openai + 凭据）后将由模型基于知识库作答。"
            )

        lines = [
            f"[Stub 模式·未接真实 LLM] 针对问题「{question}」，"
            f"检索到 {len(refs)} 条相关法律依据：",
            "",
        ]
        for n, body in refs:
            lines.append(f"[{n}] {body[:120]}")
        lines += [
            "",
            "（此为 Stub 模板答案。设置 LLM_PROVIDER=openai + LLM_API_BASE/KEY/MODEL 后，"
            "将由真实 LLM 生成完整、带 [n] 引用标注的法律回答。）",
        ]
        return "\n".join(lines)


def _call_openai_compat(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    *,
    max_tokens: int | None = None,
) -> str:
    """共用：带超时/重试/输出限制的 OpenAI 兼容 Chat Completions 调用。"""
    try:
        from openai import OpenAI
    except ImportError as e:
        raise LLMServiceError(
            "该 LLM provider 需要 openai 包：pip install openai"
        ) from e
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    request: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": settings.llm_temperature,
        "max_tokens": max_tokens or settings.llm_max_tokens,
    }
    if settings.llm_enable_thinking is not None:
        # 百炼 Qwen3.x 的非 OpenAI 标准扩展参数；其它兼容服务默认不发送。
        request["extra_body"] = {
            "enable_thinking": settings.llm_enable_thinking
        }
    try:
        resp = client.chat.completions.create(**request)
    except Exception as e:
        raise LLMServiceError(
            f"LLM provider request failed ({type(e).__name__})"
        ) from e
    content = resp.choices[0].message.content or ""
    if not content.strip():
        raise LLMServiceError(f"LLM {model} returned empty content")
    return content


class _OpenAILLM:
    """OpenAI 兼容 API（DeepSeek/智谱/通义/OpenAI）。"""

    def generate(self, prompt: str, *, max_tokens: int | None = None) -> str:
        if not (settings.llm_api_base and settings.llm_api_key and settings.llm_model):
            raise LLMServiceError(
                "LLM_PROVIDER=openai 需配置 LLM_API_BASE / LLM_API_KEY / LLM_MODEL"
            )
        return _call_openai_compat(
            settings.llm_api_base,
            settings.llm_api_key,
            settings.llm_model,
            prompt,
            max_tokens=max_tokens,
        )


class _OllamaLLM:
    """本地 Ollama（OpenAI 兼容端点 :11434/v1）。"""

    def generate(self, prompt: str, *, max_tokens: int | None = None) -> str:
        if not settings.llm_model:
            raise LLMServiceError("LLM_PROVIDER=ollama 需配置 LLM_MODEL（如 qwen2.5:7b）")
        base = settings.llm_api_base or "http://localhost:11434/v1"
        return _call_openai_compat(
            base, "ollama", settings.llm_model, prompt, max_tokens=max_tokens
        )
