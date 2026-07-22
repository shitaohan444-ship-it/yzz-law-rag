import unittest

from app.ingest.chunker import split, to_markdown


class ArticleChunkingTests(unittest.TestCase):
    def test_short_articles_are_never_merged(self) -> None:
        text = """# 示例法规
第一章 总则
第一条 第一条正文。
第二条 第二条正文。
第三条 第三条正文。"""

        chunks = split(text, chunk_size=500, overlap=64, by_article=True)
        articles = [c for c in chunks if c.article_no]

        self.assertEqual(
            [c.article_no for c in articles], ["第一条", "第二条", "第三条"]
        )
        for chunk in articles:
            self.assertTrue(chunk.text.startswith(chunk.article_no))
            self.assertEqual(chunk.text.count("条 "), 1)

    def test_article_metadata_matches_the_article_in_text(self) -> None:
        text = """第一章 一般规定
第一千一百八十二条 财产损失赔偿。
第三章 特殊责任
第一千一百九十一条 工作人员致害由单位承担责任。
第五章 产品责任
第一千二百零二条 产品缺陷致害由生产者承担责任。"""

        chunks = split(text, chunk_size=500, overlap=64, by_article=True)
        by_no = {c.article_no: c for c in chunks if c.article_no}

        self.assertIn("第一千一百九十一条", by_no)
        self.assertIn("第一千二百零二条", by_no)
        self.assertTrue(
            by_no["第一千一百九十一条"].text.startswith("第一千一百九十一条")
        )
        self.assertEqual(by_no["第一千二百零二条"].chapter, "第五章 产品责任")

    def test_long_article_subchunks_keep_the_same_metadata(self) -> None:
        body = "甲方应当履行义务，" * 80
        text = f"""第二章 合同
第十条 {body}
第十一条 下一条正文。
第十二条 最后一条正文。"""

        chunks = split(text, chunk_size=120, overlap=20, by_article=True)
        long_chunks = [c for c in chunks if c.article_no == "第十条"]

        self.assertGreater(len(long_chunks), 1)
        self.assertTrue(all(c.chapter == "第二章 合同" for c in long_chunks))
        self.assertEqual(
            len([c for c in chunks if c.article_no == "第十一条"]), 1
        )

    def test_unstructured_text_uses_recursive_fallback(self) -> None:
        chunks = split("判决书正文。" * 100, chunk_size=80, overlap=10, by_article=True)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(c.article_no is None for c in chunks))

    def test_long_text_without_separators_falls_back_to_fixed_step(self) -> None:
        """超长且不含任何分隔符的文本走定长步进兜底，不抛 empty separator。

        回归：_SEPARATORS 末尾曾有 ""，递归降到 text.split("") 会抛
        ValueError: empty separator（真实案例：香港基本法解释 docx 含超长无标点段）。
        """
        chunks = split("法" * 5000, chunk_size=1000, overlap=100, by_article=False)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.text), 1000)

    def test_article_references_in_notes_do_not_trigger_structured_chunking(self) -> None:
        text = """# 律师实务笔记
诉讼时效需要结合案件事实判断。
第一百八十九条规定，分期债务从最后一期届满时计算。
第一百九十五条规定，提出履行请求可以中断诉讼时效。
后续是证据整理和起诉流程说明。"""

        chunks = split(text, chunk_size=80, overlap=10, by_article=True)

        self.assertTrue(all(c.article_no is None for c in chunks))

    def test_part_chapter_section_article_metadata_uses_chapter_only(self) -> None:
        text = """第一编 总则
第一章 基本规定
第一节 测试范围
第一条 第一条正文。
第二节 其他范围
第二条 第二条正文。
第二章 数据安全
第一节 安全范围
第三条 第三条正文。"""

        chunks = split(text, chunk_size=500, overlap=32, by_article=True)
        by_no = {chunk.article_no: chunk for chunk in chunks if chunk.article_no}

        self.assertEqual(by_no["第一条"].chapter, "第一章 基本规定")
        self.assertEqual(by_no["第二条"].chapter, "第一章 基本规定")
        self.assertEqual(by_no["第三条"].chapter, "第二章 数据安全")

    def test_txt_part_chapter_section_article_all_become_markdown_headings(self) -> None:
        rendered = to_markdown(
            "第一编 总则\n第一章 基本规定\n第一节 测试范围\n第一条 正文。"
        )

        self.assertIn("## 第一编 总则", rendered)
        self.assertIn("## 第一章 基本规定", rendered)
        self.assertIn("## 第一节 测试范围", rendered)
        self.assertIn("### 第一条", rendered)


if __name__ == "__main__":
    unittest.main()
