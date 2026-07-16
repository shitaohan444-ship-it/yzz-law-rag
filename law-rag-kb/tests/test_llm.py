import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import settings
from app.rag.llm import LLMServiceError, _call_openai_compat


class OpenAICompatibleLlmTests(unittest.TestCase):
    @patch("openai.OpenAI")
    def test_qwen_request_uses_limits_and_disables_thinking(self, openai_mock) -> None:
        client = openai_mock.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="依据如下。[1]"))]
        )

        answer = _call_openai_compat(
            "https://example.invalid/v1", "secret", "qwen3.7-plus", "prompt"
        )

        self.assertEqual(answer, "依据如下。[1]")
        openai_mock.assert_called_once_with(
            base_url="https://example.invalid/v1",
            api_key="secret",
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "qwen3.7-plus")
        self.assertEqual(request["max_tokens"], settings.llm_max_tokens)
        self.assertEqual(
            request["extra_body"], {"enable_thinking": settings.llm_enable_thinking}
        )

    @patch("openai.OpenAI")
    def test_empty_model_response_is_an_error(self, openai_mock) -> None:
        client = openai_mock.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="  "))]
        )

        with self.assertRaisesRegex(LLMServiceError, "returned empty content"):
            _call_openai_compat(
                "https://example.invalid/v1", "secret", "qwen3.7-plus", "prompt"
            )

    @patch("openai.OpenAI")
    def test_provider_exception_is_sanitized(self, openai_mock) -> None:
        client = openai_mock.return_value
        client.chat.completions.create.side_effect = TimeoutError("contains internals")

        with self.assertRaisesRegex(
            LLMServiceError, r"provider request failed \(TimeoutError\)"
        ) as caught:
            _call_openai_compat(
                "https://example.invalid/v1", "secret", "qwen3.7-plus", "prompt"
            )

        self.assertNotIn("contains internals", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
