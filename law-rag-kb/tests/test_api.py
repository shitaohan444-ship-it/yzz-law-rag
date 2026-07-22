import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.ingest.service import DocumentNotFoundError, IngestResult
from app.rag.chat import ChatResult
from app.rag.llm import LLMServiceError
from app.rag.retrieve import SearchHit


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_openapi_exposes_all_rag_routes(self) -> None:
        paths = set(self.client.get("/openapi.json").json()["paths"])

        self.assertTrue(
            {
                "/health",
                "/ready",
                "/documents/{doc_id}/ingest",
                "/documents/{doc_id}",
                "/documents/{doc_id}/chunks",
                "/documents/batch-delete",
                "/search",
                "/chat",
            }.issubset(paths)
        )

    @patch("app.api.health._check_model_path", return_value="ok")
    @patch("app.api.health._check_milvus", return_value="ok")
    @patch("app.api.health._check_minio", return_value="ok")
    @patch("app.api.health._check_pg", return_value="ok")
    def test_ready_returns_200_when_dependencies_and_models_exist(
        self, _pg_mock, _minio_mock, _milvus_mock, _model_mock
    ) -> None:
        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["models"], {"embedding": "ok", "reranker": "ok"})

    @patch("app.api.health._check_model_path", return_value="missing")
    @patch("app.api.health._check_milvus", return_value="ok")
    @patch("app.api.health._check_minio", return_value="ok")
    @patch("app.api.health._check_pg", return_value="ok")
    def test_ready_returns_503_and_names_missing_models(
        self, _pg_mock, _minio_mock, _milvus_mock, _model_mock
    ) -> None:
        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "not_ready")
        self.assertEqual(body["models"]["embedding"], "missing")

    @patch("app.api.search.authorized_doc_ids", return_value=[16])
    @patch("app.api.search.retrieve.search")
    def test_search_serializes_article_metadata(self, search_mock, _scope_mock) -> None:
        search_mock.return_value = [
            SearchHit(
                chunk_id="16_0007",
                doc_id=16,
                doc_title="民法典合同编",
                source="法规",
                chunk_idx=7,
                text="第四百八十三条 承诺生效时合同成立。",
                score=0.98,
                article_no="第四百八十三条",
                chapter="第二章 合同的订立",
            )
        ]

        response = self.client.post(
            "/search", json={"query": "合同什么时候成立", "top_k": 3}
        )

        self.assertEqual(response.status_code, 200)
        hit = response.json()["hits"][0]
        self.assertEqual(hit["article_no"], "第四百八十三条")
        self.assertEqual(hit["chapter"], "第二章 合同的订立")
        search_mock.assert_called_once()
        args, kwargs = search_mock.call_args
        self.assertEqual(args[0], "合同什么时候成立")
        self.assertIn(16, kwargs["doc_ids"])
        self.assertEqual(kwargs["top_k"], 3)

    @patch("app.api.search.retrieve.search")
    def test_search_serializes_image_reference_metadata(self, search_mock) -> None:
        search_mock.return_value = [
            SearchHit(
                chunk_id="16:i:9",
                doc_id=16,
                doc_title="事故现场材料",
                source="案件材料",
                chunk_idx=8,
                text="[图片说明] 车辆右前方受损。",
                score=0.96,
                content_type="image_description",
                image_id=9,
                page_no=3,
                image_category="evidence_photo",
            )
        ]

        response = self.client.post("/search", json={"query": "车辆哪里受损"})

        self.assertEqual(response.status_code, 200)
        hit = response.json()["hits"][0]
        self.assertEqual(hit["content_type"], "image_description")
        self.assertEqual(hit["image_id"], 9)
        self.assertEqual(hit["page_no"], 3)

    @patch("app.api.chat.chat_service.chat")
    def test_chat_returns_answer_and_numbered_refs(self, chat_mock) -> None:
        chat_mock.return_value = ChatResult(
            answer="合同在承诺生效时成立。[1]",
            refs=[
                {
                    "ref_id": 1,
                    "chunk_id": "16_0007",
                    "doc_id": 16,
                    "doc_title": "民法典合同编",
                    "chunk_idx": 7,
                    "source": "法规",
                    "score": 0.98,
                    "article_no": "第四百八十三条",
                    "chapter": "第二章 合同的订立",
                }
            ],
            chat_log_id=42,
            hits_count=1,
        )

        response = self.client.post(
            "/chat", json={"question": "合同什么时候成立", "session_id": "s1"}
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["chat_log_id"], 42)
        self.assertEqual(body["refs"][0]["article_no"], "第四百八十三条")

    def test_empty_search_and_chat_inputs_are_rejected(self) -> None:
        self.assertEqual(self.client.post("/search", json={"query": ""}).status_code, 422)
        self.assertEqual(
            self.client.post("/chat", json={"question": ""}).status_code, 422
        )

    @patch("app.api.chat.chat_service.chat")
    def test_llm_provider_failure_returns_sanitized_502(self, chat_mock) -> None:
        chat_mock.side_effect = LLMServiceError(
            "LLM provider request failed (APITimeoutError)"
        )

        response = self.client.post("/chat", json={"question": "测试问题"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"],
            "LLM provider request failed (APITimeoutError)",
        )

    @patch("app.api.documents.ingest_service.ingest_document")
    def test_post_ingest_missing_document_returns_404(self, ingest_mock) -> None:
        ingest_mock.side_effect = DocumentNotFoundError("internal detail")

        response = self.client.post("/documents/999999/ingest")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "kb_document not found"})

    @patch("app.api.documents.ingest_service.get_document_status", return_value=None)
    def test_get_missing_document_returns_404(self, _status_mock) -> None:
        response = self.client.get("/documents/999999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "kb_document not found"})

    @patch("app.api.documents.ingest_service.ingest_document")
    def test_existing_document_ingest_returns_success(self, ingest_mock) -> None:
        ingest_mock.return_value = IngestResult(23, "success", chunk_count=6)

        response = self.client.post("/documents/23/ingest?force=true")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        ingest_mock.assert_called_once_with(23, force=True)

    @patch("app.api.documents.ingest_service.ingest_document")
    def test_successful_document_without_force_returns_skipped(self, ingest_mock) -> None:
        ingest_mock.return_value = IngestResult(
            23,
            "skipped",
            vl_status="success",
            message="already ingested (use force=true to redo)",
        )

        response = self.client.post("/documents/23/ingest")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "skipped")
        ingest_mock.assert_called_once_with(23, force=False)

    @patch("app.api.documents.ingest_service.ingest_document")
    def test_ingest_can_disable_cloud_summary_and_image_analysis(self, ingest_mock) -> None:
        ingest_mock.return_value = IngestResult(23, "success", chunk_count=2)

        response = self.client.post(
            "/documents/23/ingest?generate_description=false&analyze_images=false"
        )

        self.assertEqual(response.status_code, 200)
        ingest_mock.assert_called_once_with(
            23,
            force=False,
            generate_description=False,
            analyze_images=False,
        )

    @patch("app.api.documents.ingest_service.purge_documents")
    def test_batch_delete_purges_documents(self, purge_mock) -> None:
        purge_mock.return_value = {"purged": 2, "images_removed": 3}

        response = self.client.post("/documents/batch-delete", json={"doc_ids": [10, 11]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"purged": 2, "images_removed": 3})
        purge_mock.assert_called_once_with([10, 11])

    def test_batch_delete_rejects_invalid_payloads(self) -> None:
        self.assertEqual(
            self.client.post("/documents/batch-delete", json={"doc_ids": []}).status_code,
            422,
        )
        self.assertEqual(
            self.client.post("/documents/batch-delete", json={"doc_ids": [0]}).status_code,
            422,
        )
        self.assertEqual(
            self.client.post("/documents/batch-delete", json={"doc_ids": list(range(1, 102))}).status_code,
            422,
        )

    @patch("app.api.documents.ingest_service.ingest_document")
    def test_non_not_found_ingest_failure_remains_business_response(
        self, ingest_mock
    ) -> None:
        ingest_mock.return_value = IngestResult(
            23, "failed", message="sanitized parse failure"
        )

        response = self.client.post("/documents/23/ingest")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "failed")


if __name__ == "__main__":
    unittest.main()
