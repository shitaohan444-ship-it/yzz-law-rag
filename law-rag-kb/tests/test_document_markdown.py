"""文档 Markdown 渲染端点（GET /documents/{id}/markdown）相关测试。"""
import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core import storage
from app.ingest import chunker
from app.ingest.service import DocumentMarkdown, _render_document_markdown
from app.rag import describe, llm


class ChunkerMarkdownTests(unittest.TestCase):
    def test_chapter_and_article_promoted_to_headings(self) -> None:
        text = (
            "第二章 劳动合同的订立\n"
            "第十九条 劳动合同应当以书面形式订立。\n"
            "这是一段普通正文。"
        )
        md = chunker.to_markdown(text)

        self.assertIn("## 第二章 劳动合同的订立", md)
        self.assertIn("### 第十九条", md)
        # 条号同行的正文被保留
        self.assertIn("劳动合同应当以书面形式订立。", md)
        self.assertIn("这是一段普通正文。", md)

    def test_existing_markdown_heading_preserved(self) -> None:
        md = chunker.to_markdown("# 已有标题\n正文内容")
        self.assertIn("# 已有标题", md)
        self.assertNotIn("## # 已有标题", md)

    def test_empty_text_returns_empty(self) -> None:
        self.assertEqual(chunker.to_markdown(""), "")
        self.assertEqual(chunker.to_markdown("   "), "")


class PresignedUrlTests(unittest.TestCase):
    @patch("app.core.storage.get_minio_client")
    def test_presigned_url_uses_bucket_and_expiry(self, client_mock) -> None:
        client_mock.return_value.presigned_get_object.return_value = (
            "https://minio.local/law-firm-files/abc?X-Amz-Signature=zzz"
        )

        url = storage.presigned_url("abc.png", bucket="law-firm-files", expires_seconds=120)

        self.assertIn("law-firm-files", url)
        args, kwargs = client_mock.return_value.presigned_get_object.call_args
        self.assertEqual(args[0], "law-firm-files")
        self.assertEqual(args[1], "abc.png")
        self.assertEqual(kwargs["expires"], timedelta(seconds=120))


class DescribeTests(unittest.TestCase):
    def test_generate_description_returns_text(self) -> None:
        with patch.object(llm, "get_llm") as glm:
            glm.return_value.generate.return_value = "本文档是一份劳动合同示范文本。"
            result = describe.generate_description(
                doc_title="劳动合同", body_text="甲方与乙方约定……"
            )
        self.assertEqual(result, "本文档是一份劳动合同示范文本。")

    def test_generate_description_degrades_on_failure(self) -> None:
        with patch.object(llm, "get_llm") as glm:
            glm.return_value.generate.side_effect = llm.LLMServiceError("boom")
            result = describe.generate_description(
                doc_title="合同", body_text="正文"
            )
        self.assertIsNone(result)

    def test_generate_description_none_when_no_content(self) -> None:
        with patch.object(llm, "get_llm") as glm:
            result = describe.generate_description(doc_title="x", body_text="")
        self.assertIsNone(result)
        glm.return_value.generate.assert_not_called()


class RenderMarkdownTests(unittest.TestCase):
    @staticmethod
    def _image(**over):
        base = {
            "image_category": "diagram",
            "page_no": 3,
            "description_text": "合同争议处理流程图",
            "bucket_name": "law-firm-files",
            "object_key": "rag-derived/21/x/y.png",
        }
        base.update(over)
        return base

    def test_full_render_with_description_body_and_image(self) -> None:
        with patch("app.ingest.service.minio_presigned_url", return_value="https://minio/p.png"):
            md = _render_document_markdown(
                title="合同示范文本",
                body="第十九条 应当以书面形式订立。",
                description_summary="一份劳动合同示范文本。",
                images=[self._image()],
            )
        self.assertIn("# 合同示范文本", md)
        self.assertIn("## 文档概述", md)
        self.assertIn("一份劳动合同示范文本。", md)
        self.assertIn("## 正文", md)
        self.assertIn("### 第十九条", md)
        self.assertIn("## 附图", md)
        self.assertIn("![合同争议处理流程图](https://minio/p.png)", md)

    def test_render_without_description_or_images(self) -> None:
        md = _render_document_markdown(title="纯文本", body="正文段落", description_summary=None, images=[])
        self.assertIn("# 纯文本", md)
        self.assertIn("## 正文", md)
        self.assertNotIn("## 文档概述", md)
        self.assertNotIn("## 附图", md)

    def test_presigned_failure_does_not_break_render(self) -> None:
        with patch("app.ingest.service.minio_presigned_url", side_effect=RuntimeError("minio down")):
            md = _render_document_markdown(
                title="t", body="b", description_summary=None, images=[self._image()]
            )
        self.assertIn("## 附图", md)
        self.assertIn("图片链接生成失败", md)


class BuildMarkdownServiceTests(unittest.TestCase):
    def _row(self, **over):
        base = {
            "doc_title": "合同",
            "content_text": "第十九条 正文。",
            "description_summary": "概述文字。",
            "attachment_id": 41,
        }
        base.update(over)
        return base

    @patch("app.ingest.service._document_sources", return_value=[])
    @patch("app.ingest.service._load_kept_images", return_value=[])
    @patch("app.ingest.service._load_document")
    def test_build_markdown_assembles_sections(self, load_mock, _img_mock, _sources_mock) -> None:
        load_mock.return_value = self._row()
        result = __import__("app.ingest.service", fromlist=["build_document_markdown"]).build_document_markdown(21)
        self.assertIsNotNone(result)
        self.assertEqual(result.doc_id, 21)
        self.assertEqual(result.image_count, 0)
        self.assertIn("# 合同", result.markdown)
        self.assertIn("## 文档概述", result.markdown)
        self.assertIn("## 正文", result.markdown)

    @patch("app.ingest.service._load_kept_images", return_value=[])
    @patch("app.ingest.service._load_document", return_value=None)
    def test_build_markdown_returns_none_when_missing(self, _a, _b) -> None:
        svc = __import__("app.ingest.service", fromlist=["build_document_markdown"])
        self.assertIsNone(svc.build_document_markdown(999999))


class MarkdownApiTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.main import app
        self.client = TestClient(app)

    @patch("app.ingest.service.build_document_markdown")
    def test_get_markdown_200(self, build_mock) -> None:
        build_mock.return_value = DocumentMarkdown(
            doc_id=21,
            doc_title="合同",
            description_summary="概述",
            image_count=1,
            markdown="# 合同\n\n## 附图\n\n![x](http://minio/p.png)",
        )
        resp = self.client.get("/documents/21/markdown")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["doc_id"], 21)
        self.assertIn("# 合同", body["markdown"])
        self.assertEqual(body["image_count"], 1)

    @patch("app.ingest.service.build_document_markdown", return_value=None)
    def test_get_markdown_404(self, _build_mock) -> None:
        resp = self.client.get("/documents/999999/markdown")
        self.assertEqual(resp.status_code, 404)


class IngestDescriptionDegradationTests(unittest.TestCase):
    """文档摘要生成失败不应阻断入库。"""

    def test_generate_returns_none_when_disabled(self) -> None:
        from app.core.config import settings
        from app.ingest.document import ParsedDocument, TextBlock
        from app.ingest.service import _generate_doc_description

        original = settings.kb_generate_description
        settings.kb_generate_description = False
        try:
            result = _generate_doc_description(
                "t", ParsedDocument(text_blocks=[TextBlock("正文", 1, 0)]), []
            )
        finally:
            settings.kb_generate_description = original
        self.assertIsNone(result)

    def test_generate_passes_through_none(self) -> None:
        # describe.generate_description 内部已捕获 LLM 异常返回 None；
        # _generate_doc_description 应把 None 透传，不抛异常。
        from app.ingest.document import ParsedDocument, TextBlock
        from app.ingest.service import _generate_doc_description

        with patch.object(describe, "generate_description", return_value=None):
            result = _generate_doc_description(
                "t", ParsedDocument(text_blocks=[TextBlock("正文", 1, 0)]), []
            )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
