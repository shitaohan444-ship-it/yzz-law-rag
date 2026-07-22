from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import httpx


class ApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ApiConflict(ApiError):
    pass


class ApiTimeout(ApiError):
    pass


class PlatformClient:
    def __init__(
        self,
        api_url: str,
        *,
        timeout: float = 120.0,
        ingest_timeout: float = 1000.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.ingest_timeout = ingest_timeout
        self.client = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> PlatformClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def categories(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/rag/categories")
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ApiError("分类接口返回格式无效")
        return items

    def upload(
        self,
        *,
        path: Path,
        title: str,
        category_id: str,
        relative_path: str,
    ) -> dict[str, Any]:
        try:
            with path.open("rb") as stream:
                response = self.client.post(
                    f"{self.api_url}/api/rag/documents",
                    data={
                        "title": title,
                        "category_id": category_id,
                        "source_relative_path": relative_path,
                    },
                    files={
                        "file": (
                            path.name,
                            stream,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    },
                )
        except httpx.TimeoutException as exc:
            raise ApiTimeout("上传请求超时；可安全重试，服务端将按 SHA-256 去重") from exc
        except (httpx.HTTPError, OSError) as exc:
            raise ApiError(f"上传请求失败: {exc}") from exc
        return cast(dict[str, Any], self._decode(response))

    def ingest(self, doc_id: str) -> dict[str, Any]:
        try:
            response = self.client.post(
                f"{self.api_url}/api/rag/documents/{doc_id}/ingest",
                params={
                    "force": "false",
                    "generate_description": "false",
                    "analyze_images": "false",
                },
                timeout=self.ingest_timeout,
            )
        except httpx.TimeoutException as exc:
            raise ApiTimeout("RAG 入库请求超时，将查询文档状态后再决定是否重试") from exc
        except httpx.HTTPError as exc:
            raise ApiError(f"RAG 入库请求失败: {exc}") from exc
        return cast(dict[str, Any], self._decode(response))

    def document_status(self, doc_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/api/rag/documents/{doc_id}/status")
        if not isinstance(payload, dict):
            raise ApiError("文档状态接口返回格式无效")
        return payload

    def _request(self, method: str, path: str) -> Any:
        try:
            response = self.client.request(method, f"{self.api_url}{path}")
        except httpx.TimeoutException as exc:
            raise ApiTimeout(f"请求超时: {path}") from exc
        except httpx.HTTPError as exc:
            raise ApiError(f"请求失败: {exc}") from exc
        return self._decode(response)

    @staticmethod
    def _decode(response: httpx.Response) -> Any:
        if response.is_success:
            try:
                return response.json()
            except ValueError as exc:
                raise ApiError("平台接口返回了非 JSON 内容", response.status_code) from exc
        try:
            payload = response.json()
            detail = payload.get("message") or payload.get("detail") or payload
        except ValueError:
            detail = response.text or response.reason_phrase
        error_type = ApiConflict if response.status_code == 409 else ApiError
        raise error_type(str(detail), response.status_code)


def flatten_categories(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    stack = list(reversed(items))
    while stack:
        item = stack.pop()
        result.append(item)
        children = item.get("children")
        if isinstance(children, list):
            stack.extend(reversed(children))
    return result
