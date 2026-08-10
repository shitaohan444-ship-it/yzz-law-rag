import unittest
from unittest.mock import patch

from app.ingest import service


class IngestErrorSafetyTests(unittest.TestCase):
    @patch("app.ingest.service._set_ingest_timings")
    @patch("app.ingest.service._set_status")
    @patch("app.ingest.service.ensure_collection")
    @patch("app.ingest.service._load_document")
    def test_internal_exception_is_logged_but_not_returned_or_stored(
        self,
        load_document,
        ensure_collection,
        set_status,
        _set_timings,
    ) -> None:
        load_document.return_value = {
            "attachment_id": 7,
            "embedding_status": "pending",
            "upload_timings": None,
        }
        ensure_collection.side_effect = RuntimeError(
            r"C:\private\case.pdf postgres://user:password@internal-db"
        )

        with self.assertLogs("uvicorn.error", level="ERROR") as captured:
            result = service.ingest_document(23)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "RAG_INGEST_FAILED")
        self.assertEqual(result.message, "文档处理失败，请检查文件后重试")
        self.assertNotIn("private", result.message)
        self.assertNotIn("postgres", result.message)
        self.assertTrue(any("RAG_INGEST_FAILED" in line for line in captured.output))
        failed_write = next(
            call
            for call in set_status.call_args_list
            if len(call.args) >= 2 and call.args[1] == "failed"
        )
        self.assertEqual(failed_write.kwargs["error_code"], "RAG_INGEST_FAILED")
        self.assertNotIn("private", str(failed_write))


if __name__ == "__main__":
    unittest.main()
