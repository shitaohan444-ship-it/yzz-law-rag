from __future__ import annotations

import httpx

from law_rag_bulk.client import PlatformClient


def test_ingest_explicitly_disables_summary_and_image_analysis() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"doc_id": 9, "status": "success", "chunk_count": 3})

    with PlatformClient("http://platform", transport=httpx.MockTransport(handler)) as client:
        result = client.ingest("9")

    assert result["status"] == "success"
    assert len(requests) == 1
    query = dict(requests[0].url.params)
    assert query == {
        "force": "false",
        "generate_description": "false",
        "analyze_images": "false",
    }
