import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.ingest import service
from app.ingest.service import DocumentChunksUnavailableError
from app.ingest.timing import PipelineTimer
from app.main import app


class DocumentChunkServiceTests(unittest.TestCase):
    @patch.object(service, "_load_document", return_value={"doc_title": "测试案例"})
    @patch.object(service, "_primary_source_id", return_value=81)
    @patch.object(service, "_source_title", return_value="主文件")
    @patch.object(service, "get_milvus_client")
    def test_chunks_are_filtered_sorted_paginated_without_vectors(
        self, client_factory, _source_title, _primary_source, _load
    ) -> None:
        client = MagicMock()
        client.has_collection.return_value = True
        client.query.return_value = [
                {
                    "id": "30:m:0001",
                    "chunk_idx": 1,
                    "source": "案例",
                    "chunk_text": "第二段",
                    "meta": {"content_type": "markdown", "page_no": 2},
                },
                {
                    "id": "30:m:0000",
                    "chunk_idx": 0,
                    "source": "案例",
                    "chunk_text": "第一段",
                    "meta": {"article_no": "第一条", "content_type": "markdown"},
                },
        ]
        client_factory.return_value = client

        result = service.get_document_chunks(30, page=1, page_size=20)

        self.assertEqual(result.total, 2)
        self.assertEqual([item.chunk_id for item in result.items], ["30:m:0000", "30:m:0001"])
        self.assertEqual(result.items[0].char_count, 3)
        page_call = client.query.call_args_list[0]
        self.assertEqual(
            page_call.kwargs["output_fields"],
            ["id", "chunk_idx", "source", "chunk_text", "meta"],
        )
        self.assertNotIn("dense", page_call.kwargs["output_fields"])
        self.assertNotIn("sparse", page_call.kwargs["output_fields"])

    @patch.object(service, "_load_document", return_value={"doc_title": "测试"})
    @patch.object(service, "get_milvus_client")
    def test_invalid_milvus_response_is_unavailable(self, client_factory, _load) -> None:
        client = MagicMock()
        client.has_collection.return_value = True
        client.query.return_value = {"unexpected": True}
        client_factory.return_value = client
        with self.assertRaises(DocumentChunksUnavailableError):
            service.get_document_chunks(30)

    @patch.object(service, "_load_document", return_value=None)
    def test_missing_document_returns_none(self, _load) -> None:
        self.assertIsNone(service.get_document_chunks(999))


class DocumentChunkApiTests(unittest.TestCase):
    client = TestClient(app)

    @patch("app.api.documents.can_access_document", return_value=True)
    @patch("app.api.documents.ingest_service.get_document_chunks", return_value=None)
    def test_missing_chunk_document_is_safe_404(self, _chunks, _access) -> None:
        response = self.client.get("/documents/999/chunks")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "kb_document not found"})

    def test_chunk_pagination_is_validated(self) -> None:
        self.assertEqual(self.client.get("/documents/30/chunks?page=0").status_code, 422)
        self.assertEqual(
            self.client.get("/documents/30/chunks?page_size=101").status_code, 422
        )


class PipelineTimerTests(unittest.TestCase):
    def test_success_skipped_and_failed_stages_are_safe(self) -> None:
        timer = PipelineTimer()
        with timer.stage("prepare", "准备"):
            pass
        timer.skip("vl_analysis", "图片 VL 分析")
        with self.assertRaises(RuntimeError):
            with timer.stage("embedding", "生成向量"):
                raise RuntimeError("secret-token internal-path")
        report = timer.report("failed")
        self.assertEqual([stage["status"] for stage in report["stages"]], ["success", "skipped", "failed"])
        self.assertGreaterEqual(report["total_ms"], 0)
        self.assertNotIn("secret-token", str(report))
        self.assertNotIn("internal-path", str(report))


class StagingPromotionTests(unittest.TestCase):
    def test_promoted_chunk_keeps_vectors_and_uses_target_stable_id(self) -> None:
        record = {
            "id": "41:m:0003",
            "doc_id": 41,
            "chunk_idx": 3,
            "source": "案例",
            "chunk_text": "新版本正文",
            "dense": [0.1, 0.2],
            "sparse": {1: 0.5},
            "meta": {"doc_title": "新标题"},
        }
        promoted = service._promoted_record(record, 30)
        self.assertEqual(promoted["id"], "30:m:0003")
        self.assertEqual(promoted["doc_id"], 30)
        self.assertEqual(promoted["dense"], [0.1, 0.2])
        self.assertEqual(promoted["sparse"], {1: 0.5})

    @patch("app.api.documents.ingest_service.promote_staging_document")
    def test_service_only_promote_returns_target_result(self, promote_mock) -> None:
        promote_mock.return_value = service.IngestResult(
            30, "success", chunk_count=4
        )
        response = TestClient(app).post(
            "/documents/41/promote?target_doc_id=30"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["doc_id"], 30)
        promote_mock.assert_called_once_with(41, 30)

    @patch("app.api.documents.ingest_service.cleanup_staging_document")
    def test_staging_cleanup_is_idempotent(self, cleanup_mock) -> None:
        response = TestClient(app).delete("/documents/41/staging")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "cleaned"})
        cleanup_mock.assert_called_once_with(41)


if __name__ == "__main__":
    unittest.main()
