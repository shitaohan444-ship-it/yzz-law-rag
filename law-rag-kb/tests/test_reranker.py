import unittest
from unittest.mock import MagicMock, patch

from app.rag import reranker


class RerankerBatchingTests(unittest.TestCase):
    @patch("app.rag.reranker.get_reranker_model")
    def test_length_sorted_batches_restore_original_score_order(
        self, get_model_mock
    ) -> None:
        model = MagicMock()
        # 排序后顺序是“短”“中等文本”“这是最长的一段文本”。
        model.compute_score.return_value = [0.1, 0.2, 0.3]
        get_model_mock.return_value = model
        texts = ["这是最长的一段文本", "短", "中等文本"]

        scores = reranker.rerank("问题", texts)

        self.assertEqual(scores, [0.3, 0.1, 0.2])
        pairs = model.compute_score.call_args.args[0]
        self.assertEqual([pair[1] for pair in pairs], ["短", "中等文本", "这是最长的一段文本"])
        self.assertEqual(
            model.compute_score.call_args.kwargs["batch_size"],
            2,
        )
