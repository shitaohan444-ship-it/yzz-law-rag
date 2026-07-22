"""verify_restore_artifacts：恢复前的 RAG 侧派生产物完整性校验。"""
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.ingest import service
from app.main import app


def _session_factory(doc_rows, image_rows):
    """构造 SessionLocal() 的返回值（上下文管理器）：with SessionLocal() as db: ..."""
    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.side_effect = [
        doc_rows,
        image_rows,
    ]
    ctx = MagicMock()
    ctx.__enter__.return_value = db
    ctx.__exit__.return_value = False
    return ctx


class VerifyRestoreArtifactsTests(unittest.TestCase):
    @patch.object(service, "SessionLocal")
    @patch.object(service, "minio_file_exists", return_value=True)
    @patch.object(service, "_count_chunks_strict", return_value=3)
    def test_intact_success_doc_is_ok(
        self, count_mock, fileexists_mock, session_factory
    ) -> None:
        session_factory.return_value = _session_factory(
            doc_rows=[{"id": 30, "embedding_status": "success"}],
            image_rows=[
                {"document_id": 30, "bucket_name": "law-firm-files", "object_key": "rag-derived/30/x/a.png"}
            ],
        )

        result = service.verify_restore_artifacts([30])

        self.assertEqual(result["items"][0]["doc_id"], 30)
        self.assertTrue(result["items"][0]["ok"])
        self.assertEqual(result["items"][0]["missing_chunks"], 0)
        self.assertEqual(result["items"][0]["missing_images"], [])
        count_mock.assert_called_once_with(30)
        fileexists_mock.assert_called_once_with(
            "rag-derived/30/x/a.png", "law-firm-files"
        )

    @patch.object(service, "SessionLocal")
    @patch.object(service, "minio_file_exists", return_value=True)
    @patch.object(service, "_count_chunks_strict", return_value=0)
    def test_missing_chunks_is_not_ok(
        self, count_mock, _fileexists_mock, session_factory
    ) -> None:
        session_factory.return_value = _session_factory(
            doc_rows=[{"id": 30, "embedding_status": "success"}],
            image_rows=[],
        )

        result = service.verify_restore_artifacts([30])

        self.assertFalse(result["items"][0]["ok"])
        self.assertEqual(result["items"][0]["missing_chunks"], 1)

    @patch.object(service, "SessionLocal")
    @patch.object(service, "minio_file_exists", return_value=False)
    @patch.object(service, "_count_chunks_strict", return_value=2)
    def test_missing_image_object_is_not_ok(
        self, _count_mock, _fileexists_mock, session_factory
    ) -> None:
        session_factory.return_value = _session_factory(
            doc_rows=[{"id": 30, "embedding_status": "success"}],
            image_rows=[
                {"document_id": 30, "bucket_name": "law-firm-files", "object_key": "rag-derived/30/x/a.png"},
                {"document_id": 30, "bucket_name": "law-firm-files", "object_key": "rag-derived/30/x/b.png"},
            ],
        )

        result = service.verify_restore_artifacts([30])

        self.assertFalse(result["items"][0]["ok"])
        self.assertEqual(
            result["items"][0]["missing_images"],
            ["rag-derived/30/x/a.png", "rag-derived/30/x/b.png"],
        )

    @patch.object(service, "SessionLocal")
    @patch.object(service, "minio_file_exists")
    @patch.object(service, "_count_chunks_strict")
    def test_non_success_doc_skips_chunk_check(
        self, count_mock, fileexists_mock, session_factory
    ) -> None:
        # pending 文档从未生成向量，恢复时跳过 chunk 校验；只要图片在即 ok。
        session_factory.return_value = _session_factory(
            doc_rows=[{"id": 31, "embedding_status": "pending"}],
            image_rows=[],
        )
        fileexists_mock.return_value = True

        result = service.verify_restore_artifacts([31])

        self.assertTrue(result["items"][0]["ok"])
        self.assertEqual(result["items"][0]["missing_chunks"], 0)
        count_mock.assert_not_called()

    @patch.object(service, "SessionLocal")
    def test_empty_input_short_circuits(self, session_factory) -> None:
        result = service.verify_restore_artifacts([])
        self.assertEqual(result, {"items": []})
        session_factory.assert_not_called()


class VerifyRestoreApiTests(unittest.TestCase):
    client = TestClient(app)

    @patch(
        "app.api.documents.ingest_service.verify_restore_artifacts",
        return_value={
            "items": [
                {"doc_id": 30, "ok": True, "missing_chunks": 0, "missing_images": []}
            ]
        },
    )
    def test_verify_restore_returns_items(self, verify_mock) -> None:
        response = self.client.post("/documents/verify-restore", json={"doc_ids": [30]})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["items"][0]["doc_id"], 30)
        self.assertTrue(body["items"][0]["ok"])
        verify_mock.assert_called_once_with([30])

    def test_verify_restore_validates_doc_ids(self) -> None:
        self.assertEqual(
            self.client.post("/documents/verify-restore", json={"doc_ids": []}).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                "/documents/verify-restore", json={"doc_ids": [0]}
            ).status_code,
            422,
        )


if __name__ == "__main__":
    unittest.main()
