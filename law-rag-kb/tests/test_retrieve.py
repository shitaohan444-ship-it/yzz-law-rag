import unittest
from unittest.mock import patch

from app.rag import retrieve


class LegalQueryNormalizationTests(unittest.TestCase):
    def test_manufacturer_and_direct_liability_phrases_are_normalized(self) -> None:
        cases = {
            "产品缺陷造成损害生产厂家要赔吗": "产品缺陷造成损害生产者承担侵权责任",
            "产品有缺陷造成损害，生产者是否赔偿": "产品有缺陷造成损害，生产者承担侵权责任",
            "厂家生产的产品致人损害谁负责": "生产者生产的产品致人损害谁承担侵权责任",
            "产品缺陷导致消费者受伤可以找生产厂家吗": "产品缺陷导致消费者受伤生产者承担侵权责任",
            "生产商对缺陷产品承担什么责任": "生产者对缺陷产品承担侵权责任",
        }

        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(retrieve.normalize_legal_query(query), expected)

    def test_unrelated_compensation_scope_query_is_not_rewritten(self) -> None:
        query = "撞伤人要赔哪些费用"

        self.assertEqual(retrieve.normalize_legal_query(query), query)

    @patch("app.rag.retrieve.reranker.rerank", return_value=[0.9])
    @patch("app.rag.retrieve.hybrid_recall")
    def test_search_uses_original_query_for_recall_and_normalized_for_reranker(
        self, recall_mock, rerank_mock
    ) -> None:
        recall_mock.return_value = [
            retrieve._RecallHit(
                chunk_id="15:m:0012",
                doc_id=15,
                chunk_idx=12,
                source="法规",
                text="因产品存在缺陷造成他人损害的，生产者应当承担侵权责任。",
                meta={
                    "doc_title": "民法典侵权责任编",
                    "article_no": "第一千二百零二条",
                },
                distance=0.03,
            )
        ]
        query = "产品缺陷造成损害生产厂家要赔吗"

        hits = retrieve.search(query, top_k=1)

        recall_mock.assert_called_once_with(query, limit=8, doc_ids=None)
        rerank_mock.assert_called_once_with(
            "产品缺陷造成损害生产者承担侵权责任",
            ["因产品存在缺陷造成他人损害的，生产者应当承担侵权责任。"],
        )
        self.assertEqual(hits[0].article_no, "第一千二百零二条")


if __name__ == "__main__":
    unittest.main()
