"""统一 Markdown → draft 切片 → VL → 最终切片管线测试。"""
from io import BytesIO
import unittest
from unittest.mock import MagicMock, patch

from docx import Document
from PIL import Image

from app.ingest import cleaner, markdown_builder, parser
from app.ingest.document import ContentNode, ImageAnalysis, ImageAsset, ParsedDocument
from app.ingest.service import _build_markdown_vector_chunks
from app.rag import markdown as markdown_utils


def _png() -> bytes:
    out = BytesIO()
    Image.new("RGB", (20, 20), "white").save(out, format="PNG")
    return out.getvalue()


def _asset(*, page_no: int | None = 3) -> ImageAsset:
    return ImageAsset(
        content=_png(),
        page_no=page_no,
        page_numbers=[page_no] if page_no else [],
        image_index=0,
        width=20,
        height=20,
        mime_type="image/png",
        extension="png",
    )


class ConversionTests(unittest.TestCase):
    def test_native_markdown_preserves_structural_whitespace(self) -> None:
        source = "# 原标题\n\n- 列表\n  - 子项\n\n```python\n  print('x')\n```"
        parsed = cleaner.clean(parser.parse(source.encode(), "md"))
        initial = markdown_builder.build_initial_markdown("包装标题", parsed, {})

        self.assertIn("  - 子项", initial)
        self.assertIn("  print('x')", initial)
        drafts = markdown_builder.split_markdown_draft(
            initial, chunk_size=500, overlap=32
        )
        self.assertTrue(drafts)
        self.assertTrue(all(item.text.startswith("# 包装标题") for item in drafts))

    def test_native_markdown_plain_article_line_gets_metadata(self) -> None:
        source = "第一千二百零二条 因产品缺陷造成损害，生产者承担责任。"
        parsed = cleaner.clean(parser.parse(source.encode(), "md"))
        initial = markdown_builder.build_initial_markdown("民法典", parsed, {})
        drafts = markdown_builder.split_markdown_draft(
            initial, chunk_size=500, overlap=32
        )
        self.assertIn("### 第一千二百零二条", initial)
        self.assertEqual(drafts[0].article_no, "第一千二百零二条")

    def test_docx_preserves_paragraph_table_image_order(self) -> None:
        doc = Document()
        doc.add_paragraph("表格前正文")
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "名称"
        table.cell(0, 1).text = "金额"
        table.cell(1, 0).text = "服务费"
        table.cell(1, 1).text = "100"
        doc.add_picture(BytesIO(_png()))
        output = BytesIO()
        doc.save(output)

        parsed = parser.parse(output.getvalue(), "docx")
        kinds = [node.kind for node in parsed.nodes]
        self.assertEqual(kinds[:3], ["text", "table", "image"])
        self.assertIn("| 名称 | 金额 |", parsed.nodes[1].text)


class MarkdownChunkingTests(unittest.TestCase):
    def _initial_with_article_and_image(self):
        asset = _asset()
        text = "第二章 合同履行\n第十九条 当事人应当履行合同义务。"
        document = ParsedDocument(
            images=[asset],
            nodes=[
                ContentNode(kind="text", text=text, page_no=1, order=0),
                ContentNode(
                    kind="image",
                    page_no=3,
                    order=1,
                    image_sha256=asset.sha256,
                ),
            ],
            metadata={"file_type": "txt"},
        )
        return asset, markdown_builder.build_initial_markdown(
            "合同", document, {asset.sha256: 8}
        )

    def test_image_is_draft_after_split_and_not_last_article_metadata(self) -> None:
        _, initial = self._initial_with_article_and_image()
        drafts = markdown_builder.split_markdown_draft(
            initial, chunk_size=500, overlap=32
        )

        article = next(item for item in drafts if item.article_no)
        image = next(item for item in drafts if item.image_ids)
        self.assertEqual(article.article_no, "第十九条")
        self.assertIsNone(image.article_no)
        self.assertEqual(image.image_ids, (8,))
        context = markdown_builder.image_contexts(drafts)[8]
        self.assertIn("当事人应当履行合同义务", context)

    def test_vl_description_and_ocr_are_enriched_but_category_is_not(self) -> None:
        asset, initial = self._initial_with_article_and_image()
        analysis = ImageAnalysis(
            asset=asset,
            status="success",
            category="diagram",
            keep_for_rag=True,
            description="合同争议处理流程",
            extracted_text="协商→仲裁→诉讼",
        )

        result = markdown_builder.enrich_markdown(initial, {8: analysis})
        self.assertIn("![合同争议处理流程](#img:8)", result)
        self.assertIn("**图片说明：** 合同争议处理流程", result)
        self.assertIn("**图片识别文字：** 协商→仲裁→诉讼", result)
        self.assertNotIn("diagram", result)

    def test_filtered_image_is_removed(self) -> None:
        asset, initial = self._initial_with_article_and_image()
        filtered = ImageAnalysis(
            asset=asset,
            status="filtered",
            category="decorative_logo",
            keep_for_rag=False,
        )
        self.assertNotIn("#img:8", markdown_builder.enrich_markdown(initial, {8: filtered}))

    def test_long_image_description_repeats_image_reference(self) -> None:
        asset, initial = self._initial_with_article_and_image()
        drafts = markdown_builder.split_markdown_draft(
            initial, chunk_size=240, overlap=20
        )
        analysis = ImageAnalysis(
            asset=asset,
            status="success",
            keep_for_rag=True,
            description="流程说明。" * 100,
        )
        enriched = markdown_builder.enrich_drafts(drafts, {8: analysis})
        final = markdown_builder.finalize_chunks(
            enriched,
            description_summary=None,
            doc_title="合同",
            chunk_size=240,
            overlap=20,
        )
        image_chunks = [item for item in final if item.image_ids]
        self.assertGreater(len(image_chunks), 1)
        self.assertTrue(all("#img:8" in item.text for item in image_chunks))
        self.assertTrue(all(item.text.startswith("# 合同") for item in image_chunks))

    def test_summary_is_independent_and_markdown_vectors_use_new_contract(self) -> None:
        draft = markdown_builder.DraftChunk(0, "# 合同\n\n## 正文\n\n正文")
        chunks = markdown_builder.finalize_chunks(
            [draft],
            description_summary="源文件概述",
            doc_title="合同",
            chunk_size=500,
            overlap=20,
        )
        self.assertIn("## 文档概述", chunks[0].text)
        self.assertNotIn("源文件概述", chunks[1].text)
        vectors = _build_markdown_vector_chunks(7, chunks, {})
        self.assertEqual(vectors[0].stable_id, "7:m:0000")
        self.assertTrue(all(item.content_type == "markdown" for item in vectors))

    def test_part_chapter_section_hierarchy_keeps_chapter_metadata(self) -> None:
        source = """第一编 总则
第一章 基本规定
第一节 测试范围
第一条 第一条正文。
第二条 第二条正文。
第二节 补充范围
第三条 第三条正文。
第二章 数据安全
第一节 安全要求
第四条 第四条正文。"""
        document = ParsedDocument(
            nodes=[ContentNode(kind="text", order=0, text=source, page_no=1)],
            metadata={"file_type": "txt"},
        )
        initial = markdown_builder.build_initial_markdown("测试法规", document, {})
        drafts = markdown_builder.split_markdown_draft(
            initial, chunk_size=500, overlap=32
        )
        by_no = {draft.article_no: draft for draft in drafts if draft.article_no}

        self.assertEqual(by_no["第一条"].chapter, "第一章 基本规定")
        self.assertEqual(by_no["第二条"].chapter, "第一章 基本规定")
        self.assertEqual(by_no["第三条"].chapter, "第一章 基本规定")
        self.assertEqual(by_no["第四条"].chapter, "第二章 数据安全")
        self.assertIn("## 第一编 总则", by_no["第一条"].text)
        self.assertIn("## 第一章 基本规定", by_no["第一条"].text)
        self.assertIn("## 第一节 测试范围", by_no["第一条"].text)
        self.assertIn("### 第一条", by_no["第一条"].text)

    def test_switching_section_does_not_change_chapter(self) -> None:
        markdown = """# 测试法规

## 正文

## 第一章 基本规定

## 第一节 范围一

### 第一条

正文一。

## 第二节 范围二

### 第二条

正文二。"""
        drafts = markdown_builder.split_markdown_draft(
            markdown, chunk_size=500, overlap=32
        )
        articles = [draft for draft in drafts if draft.article_no]

        self.assertEqual([draft.chapter for draft in articles], [
            "第一章 基本规定",
            "第一章 基本规定",
        ])
        self.assertIn("第二节 范围二", articles[1].text)
        self.assertNotIn("第一节 范围一", articles[1].text)

    def test_new_chapter_clears_previous_section_context(self) -> None:
        markdown = """# 测试法规

## 正文

## 第一章 基本规定

## 第一节 旧范围

### 第一条

正文一。

## 第二章 数据安全

### 第二条

正文二。"""
        drafts = markdown_builder.split_markdown_draft(
            markdown, chunk_size=500, overlap=32
        )
        second = next(draft for draft in drafts if draft.article_no == "第二条")

        self.assertEqual(second.chapter, "第二章 数据安全")
        self.assertIn("第二章 数据安全", second.text)
        self.assertNotIn("第一节 旧范围", second.text)

    def test_trailing_image_keeps_hierarchy_but_not_article_metadata(self) -> None:
        _, initial = self._initial_with_article_and_image()
        drafts = markdown_builder.split_markdown_draft(
            initial, chunk_size=500, overlap=32
        )
        image = next(draft for draft in drafts if draft.image_ids)

        self.assertIsNone(image.article_no)
        self.assertEqual(image.chapter, "第二章 合同履行")


class PipelineOrderTests(unittest.TestCase):
    def test_ingest_splits_before_vl_and_embeds_after_enrichment(self) -> None:
        from app.ingest import service

        events: list[str] = []
        asset = _asset()
        document = ParsedDocument(
            images=[asset],
            nodes=[ContentNode("image", 0, page_no=3, image_sha256=asset.sha256)],
            metadata={"file_type": "png"},
        )
        analysis = ImageAnalysis(asset, "success", keep_for_rag=True, description="图示")
        draft = markdown_builder.DraftChunk(0, "# 图\n\n### 第3页图片\n![待识别图片](#img:8)", image_ids=(8,))
        enriched = markdown_builder.DraftChunk(0, "# 图\n\n![图示](#img:8)\n\n图示", image_ids=(8,))
        final = markdown_builder.MarkdownChunk(0, enriched.text, image_ids=(8,))
        row = {
            "id": 7, "doc_title": "图", "doc_type": "图片", "legal_category": None,
            "attachment_id": 3, "content_text": None, "description_summary": None,
            "body_markdown": None, "embedding_status": "pending", "permission_level": "public",
            "source_type": "knowledge_base", "biz_type": None, "biz_id": None,
            "case_id": None, "dossier_no": None, "extra_metadata": {},
            "vl_status": "not_processed", "image_total": 0, "image_kept": 0,
            "image_filtered": 0,
        }
        client = MagicMock()

        def mark(name, value):
            def side(*args, **kwargs):
                events.append(name)
                return value
            return side

        with (
            patch.object(service, "ensure_collection"),
            patch.object(service, "_load_document", return_value=row),
            patch.object(service, "_set_status") as status_mock,
            patch.object(service, "_set_ingest_timings"),
            patch.object(service, "_set_vl_summary"),
            patch.object(service, "_resolve_document", return_value=(document, "hash")),
            patch.object(service.cleaner, "clean", return_value=document),
            patch.object(service.image_filter, "deduplicate", return_value=[asset]),
            patch.object(service, "_store_pending_images", return_value=({asset.sha256: 8}, {asset.sha256})),
            patch.object(service.markdown_builder, "build_initial_markdown", side_effect=mark("build", draft.text)),
            patch.object(service.markdown_builder, "split_markdown_draft", side_effect=mark("split", [draft])),
            patch.object(service.markdown_builder, "image_contexts", return_value={8: draft.text}),
            patch.object(service, "_analyze_images_after_draft", side_effect=mark("vl", [analysis])),
            patch.object(service, "_update_image_analyses"),
            patch.object(service, "_generate_doc_description", return_value="概述"),
            patch.object(service.markdown_builder, "enrich_drafts", side_effect=mark("enrich", [enriched])),
            patch.object(service.markdown_builder, "finalize_chunks", side_effect=mark("finalize", [final])),
            patch.object(service.markdown_builder, "enrich_markdown", return_value="# 图\n\n## 文档概述\n\n概述"),
            patch.object(service.embedding, "encode_batch", side_effect=mark("embedding", ([[0.0]], [{}]))),
            patch.object(service, "get_milvus_client", return_value=client),
        ):
            result = service.ingest_document(7, force=True)

        self.assertEqual(result.status, "success")
        self.assertEqual(events, ["build", "split", "vl", "enrich", "finalize", "embedding"])
        final_status = status_mock.call_args_list[-1].kwargs
        self.assertIn("## 文档概述", final_status["body_markdown"])
        self.assertEqual(client.upsert.call_args.kwargs["data"][0]["id"], "7:m:0000")


class MarkdownReadTests(unittest.TestCase):
    def test_llm_projection_removes_urls_but_keeps_description(self) -> None:
        text = "# 标题\n\n![流程](https://minio/x?a=1)\n\n**图片说明：** 争议流程"
        projected = markdown_utils.strip_for_llm(text)
        self.assertNotIn("https://", projected)
        self.assertIn("流程", projected)
        self.assertIn("图片说明： 争议流程", projected)


if __name__ == "__main__":
    unittest.main()
