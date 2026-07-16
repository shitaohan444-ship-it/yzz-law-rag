from io import BytesIO
import json
import unittest
from unittest.mock import patch

import fitz
from docx import Document
from PIL import Image, ImageDraw

from app.core.config import settings
from app.ingest import cleaner, image_filter, parser, vl
from app.ingest.document import ImageAnalysis, ImageAsset, ParsedDocument, TextBlock
from app.ingest.service import _build_vector_chunks


def _png(*, color="white", text: str | None = None) -> bytes:
    image = Image.new("RGB", (240, 120), color)
    if text:
        ImageDraw.Draw(image).text((20, 40), text, fill="black")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _asset(content: bytes, *, page_no=1, index=0, scan=False) -> ImageAsset:
    with Image.open(BytesIO(content)) as image:
        width, height = image.size
    return ImageAsset(
        content=content,
        page_no=page_no,
        page_numbers=[page_no],
        image_index=index,
        width=width,
        height=height,
        mime_type="image/png",
        extension="png",
        nearby_text="合同附件图片",
        is_page_scan=scan,
    )


def _vl_response(payload: dict, *, finish_reason="stop"):
    """构造 _request 的 4 元组返回值：(content, prompt_tokens, completion_tokens, finish_reason)。"""
    return (json.dumps(payload, ensure_ascii=False), 10, 20, finish_reason)


class StructuredParserTests(unittest.TestCase):
    def test_standalone_image_becomes_image_document(self) -> None:
        parsed = parser.parse(_png(text="evidence"), "png")

        self.assertEqual(parsed.text, "")
        self.assertEqual(len(parsed.images), 1)
        self.assertEqual(parsed.images[0].page_no, 1)

    def test_pdf_keeps_text_page_and_embedded_image(self) -> None:
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((30, 30), "contract evidence " * 10)
        page.insert_image(fitz.Rect(30, 60, 270, 180), stream=_png(text="chart"))
        content = pdf.tobytes()
        pdf.close()

        parsed = parser.parse(content, "pdf", scan_page_min_text_chars=40)

        self.assertIn("contract evidence", parsed.text)
        self.assertEqual(len(parsed.images), 1)
        self.assertFalse(parsed.images[0].is_page_scan)

    def test_scan_only_pdf_is_rendered_as_page_image(self) -> None:
        pdf = fitz.open()
        page = pdf.new_page(width=240, height=120)
        page.insert_image(page.rect, stream=_png(text="scanned page"))
        content = pdf.tobytes()
        pdf.close()

        parsed = parser.parse(content, "pdf", scan_page_min_text_chars=40)

        self.assertEqual(parsed.text, "")
        self.assertEqual(len(parsed.images), 1)
        self.assertTrue(parsed.images[0].is_page_scan)

    def test_docx_preserves_paragraph_and_image_order(self) -> None:
        doc = Document()
        doc.add_paragraph("图片前正文")
        doc.add_picture(BytesIO(_png(text="seal")))
        output = BytesIO()
        doc.save(output)

        parsed = parser.parse(output.getvalue(), "docx")

        self.assertIn("图片前正文", parsed.text)
        self.assertEqual(len(parsed.images), 1)
        self.assertEqual(parsed.images[0].nearby_text, "图片前正文")


class CleaningAndPrefilterTests(unittest.TestCase):
    def test_cleaner_removes_repeated_header_footer_but_keeps_body(self) -> None:
        blocks = [
            TextBlock(
                text=f"某律师事务所\n第{page}页案件正文\n内部资料",
                page_no=page,
                order=page,
            )
            for page in range(1, 4)
        ]
        cleaned = cleaner.clean(ParsedDocument(text_blocks=blocks))

        self.assertNotIn("某律师事务所", cleaned.text)
        self.assertNotIn("内部资料", cleaned.text)
        self.assertIn("第2页案件正文", cleaned.text)

    def test_duplicate_images_are_merged_with_all_pages(self) -> None:
        content = _png(text="same")
        images = [_asset(content, page_no=1), _asset(content, page_no=3, index=1)]

        unique = image_filter.deduplicate(images)

        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0].page_numbers, [1, 3])

    def test_solid_image_is_filtered_without_vl(self) -> None:
        decision = image_filter.prefilter(_asset(_png(color="white")))

        self.assertIsNotNone(decision)
        self.assertFalse(decision.keep_for_rag)
        self.assertEqual(decision.filter_reason, "solid_color")


class JsonParserTests(unittest.TestCase):
    """直接测试 vl._parse_payload 对各种响应包装与轻微格式问题的鲁棒性。"""

    _DIAGRAM = {
        "category": "diagram",
        "keep_for_rag": True,
        "confidence": 0.93,
        "description": "合同争议处理流程图，依次为协商、调解、仲裁、诉讼。",
        "extracted_text": "协商 调解 仲裁 诉讼",
        "filter_reason": "",
    }

    def test_pure_json_object_parses(self) -> None:
        payload, meta = vl._parse_payload(json.dumps(self._DIAGRAM), finish_reason="stop")

        self.assertEqual(payload["category"], "diagram")
        self.assertTrue(meta["balanced"])

    def test_markdown_code_fence_parses(self) -> None:
        content = "```json\n" + json.dumps(self._DIAGRAM, ensure_ascii=False) + "\n```"

        payload, _ = vl._parse_payload(content, finish_reason="stop")

        self.assertEqual(payload["category"], "diagram")

    def test_json_with_surrounding_explanation_parses(self) -> None:
        body = json.dumps(self._DIAGRAM, ensure_ascii=False)
        content = f"好的，以下是该图片的分析结果：\n{body}\n请注意，该流程图对案件事实认定较为关键。"

        payload, _ = vl._parse_payload(content, finish_reason="stop")

        self.assertEqual(payload["category"], "diagram")
        # 只取 JSON 对象本身；前后说明文字不得污染字段。
        self.assertEqual(payload["description"], self._DIAGRAM["description"])
        self.assertNotIn("请注意", payload["description"])

    def test_content_as_block_list_parses(self) -> None:
        # 个别 SDK 版本可能把 message.content 返回为内容块数组。
        content = [
            {"type": "text", "text": "分析结果如下"},
            {"type": "text", "text": json.dumps(self._DIAGRAM, ensure_ascii=False)},
        ]

        payload, meta = vl._parse_payload(content, finish_reason="stop")

        self.assertEqual(payload["category"], "diagram")
        self.assertEqual(meta["resp_type"], "list")

    def test_trailing_comma_is_repaired(self) -> None:
        content = (
            '{"category":"diagram","keep_for_rag":true,"confidence":0.9,'
            '"description":"流程图","extracted_text":"","filter_reason":"",}'
        )

        payload, meta = vl._parse_payload(content, finish_reason="stop")

        self.assertEqual(payload["category"], "diagram")
        self.assertTrue(meta["repaired"])

    def test_raw_newline_inside_string_is_repaired(self) -> None:
        # VL 描述多步流程时常把字面换行写进字符串值，导致 JSONDecodeError。
        # 这里 description 的值含一个真实的换行字符（Python 源里的 \n 即字面 0x0A）。
        content = (
            '{"category":"diagram","keep_for_rag":true,"confidence":0.9,'
            '"description":"第一步：协商\n第二步：调解\n第三步：仲裁",'
            '"extracted_text":"","filter_reason":""}'
        )

        payload, meta = vl._parse_payload(content, finish_reason="stop")

        self.assertTrue(meta["repaired"])
        self.assertEqual(payload["description"], "第一步：协商\n第二步：调解\n第三步：仲裁")

    def test_smart_quote_delimiters_are_normalized(self) -> None:
        # 真实根因：qwen3-vl-plus 偶发用 Unicode 弯引号 “ ” 包裹个别键，替代 ASCII 双引号，
        # 导致 json.loads 报 "Expecting property name enclosed in double quotes"。
        content = (
            '{"category":"diagram","keep_for_rag":true,"confidence":0.95,'
            '"description":"合同争议处理流程图","extracted_text":"协商→调解→仲裁",'
            "“filter_reason”:" + '""}'
        )

        payload, meta = vl._parse_payload(content, finish_reason="stop")

        self.assertEqual(payload["category"], "diagram")
        self.assertEqual(payload["filter_reason"], "")
        self.assertTrue(meta["repaired"])

    def test_content_smart_quotes_are_preserved(self) -> None:
        # ASCII 双引号定界的合法 JSON 里，正文中的弯引号不得被归一化器误伤。
        content = (
            '{"category":"other","keep_for_rag":true,"confidence":0.5,'
            '"description":"当事人表示“同意调解”","extracted_text":"","filter_reason":""}'
        )

        payload, _ = vl._parse_payload(content, finish_reason="stop")

        self.assertIn("“同意调解”", payload["description"])

    def test_truncated_json_raises_with_diagnostics(self) -> None:
        # finish_reason=length 且花括号未配平 → 视为截断。
        content = (
            '{"category":"diagram","keep_for_rag":true,"confidence":0.9,'
            '"description":"合同争议处理流程图，详细描述各节点 SECRET_CASE_BODY'
        )

        with self.assertRaises(vl._PayloadParseError) as ctx:
            vl._parse_payload(content, finish_reason="length")

        meta = ctx.exception.meta
        self.assertFalse(meta["balanced"])
        self.assertEqual(meta["finish_reason"], "length")
        self.assertEqual(meta["reason"], "json_decode_failed")


class VisionPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_key = settings.vl_api_key
        settings.vl_api_key = "test-key"

    def tearDown(self) -> None:
        settings.vl_api_key = self._original_key

    @patch("app.ingest.vl._request")
    def test_high_confidence_logo_is_not_searchable(self, request_mock) -> None:
        request_mock.return_value = _vl_response(
            {
                "category": "decorative_logo",
                "keep_for_rag": True,
                "confidence": 0.98,
                "description": "页眉品牌标志",
                "extracted_text": "",
                "filter_reason": "装饰性Logo",
            }
        )

        result = vl.analyze(_asset(_png(text="logo")), doc_title="测试文档")

        self.assertFalse(result.keep_for_rag)
        self.assertEqual(result.category, "decorative_logo")

    @patch("app.ingest.vl._request")
    def test_important_legal_image_is_always_kept(self, request_mock) -> None:
        request_mock.return_value = _vl_response(
            {
                "category": "stamp_seal",
                "keep_for_rag": False,
                "confidence": 0.99,
                "description": "合同落款处公章",
                "extracted_text": "甲公司",
                "filter_reason": "",
            }
        )

        result = vl.analyze(_asset(_png(text="seal")), doc_title="合同")

        self.assertTrue(result.keep_for_rag)
        self.assertIn("甲公司", result.searchable_text)

    @patch("app.ingest.vl._request")
    def test_diagram_kept_even_when_model_says_drop(self, request_mock) -> None:
        # 模型错误地建议丢弃法律重要图片；安全策略必须 override。
        request_mock.return_value = _vl_response(
            {
                "category": "diagram",
                "keep_for_rag": False,
                "confidence": 0.95,
                "description": "合同争议处理流程图",
                "extracted_text": "协商 调解 仲裁",
                "filter_reason": "图片较复杂",
            }
        )

        result = vl.analyze(_asset(_png(text="diagram")), doc_title="合同")

        self.assertTrue(result.keep_for_rag)
        self.assertEqual(result.category, "diagram")

    @patch("app.ingest.vl._request")
    def test_invalid_json_is_retried_once(self, request_mock) -> None:
        request_mock.side_effect = [
            ("not json", None, None, None),
            _vl_response(
                {
                    "category": "other",
                    "keep_for_rag": True,
                    "confidence": 0.5,
                    "description": "有效图片",
                    "extracted_text": "",
                    "filter_reason": "",
                }
            ),
        ]

        result = vl.analyze(_asset(_png(text="other")), doc_title="文档")

        self.assertEqual(request_mock.call_count, 2)
        self.assertTrue(result.keep_for_rag)

    @patch("app.ingest.vl._request")
    def test_truncated_response_raises_sanitized_error(self, request_mock) -> None:
        secret = "SECRET_CASE_BODY_THAT_MUST_NOT_LEAK"
        truncated = (
            '{"category":"diagram","keep_for_rag":true,"confidence":0.9,'
            f'"description":"流程图{secret}'
        )
        request_mock.return_value = (truncated, 10, 20, "length")

        with self.assertRaises(vl.VisionClientError) as ctx:
            vl.analyze(_asset(_png(text="diagram")), doc_title="文档")

        message = str(ctx.exception)
        self.assertIn("truncated=True", message)
        self.assertIn("finish_reason=length", message)
        # 错误信息不得回显正文/密钥/图片内容。
        self.assertNotIn(secret, message)
        self.assertNotIn("test-key", message)

    def test_text_is_still_ingested_when_vl_fails(self) -> None:
        # 单张图片 VL 失败时，正文仍应正常切片入库（降级机制）。
        asset = _asset(_png(text="diagram"), page_no=4)
        failed = vl.failed_analysis(asset, vl.VisionClientError("boom"))
        document = ParsedDocument(text_blocks=[TextBlock("合同正文内容，应当被切片入库。", 1, 0)])

        chunks = _build_vector_chunks(7, document, [failed], {asset.sha256: 99})

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].content_type, "text")
        self.assertEqual(chunks[0].stable_id, "7:t:0000")

    def test_image_description_uses_stable_independent_chunk(self) -> None:
        asset = _asset(_png(text="diagram"), page_no=4)
        analysis = ImageAnalysis(
            asset=asset,
            status="success",
            category="diagram",
            keep_for_rag=True,
            description="事故责任关系图",
        )
        document = ParsedDocument(text_blocks=[TextBlock("正文", 1, 0)])

        chunks = _build_vector_chunks(7, document, [analysis], {asset.sha256: 99})

        self.assertEqual(chunks[0].stable_id, "7:t:0000")
        self.assertEqual(chunks[1].stable_id, "7:i:99")
        self.assertEqual(chunks[1].content_type, "image_description")
        self.assertEqual(chunks[1].page_no, 4)


if __name__ == "__main__":
    unittest.main()
