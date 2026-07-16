"""召回质量评估：评估集 → hit@k / MRR。

直接调 retrieve.search（反映当前 config：ranker / rerank_min_score / 切片策略），
用于阶段 6 各优化（6.1 阈值 / 6.3 切片 / 6.4 权重）的前后对比。

指标：
- hit@k : 期望文档出现在 top-k 的 case 占比
- MRR  : 期望文档倒数排名的均值（1/rank，未命中=0）

用法（在 law-rag-kb 目录）：
    HF_HUB_OFFLINE=1 python scripts/eval_retrieval.py
"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from app.core.config import settings  # noqa: E402
from app.rag import retrieve  # noqa: E402

# 评估集：(query, expected_doc_title)。expected 命中即算（doc_title 匹配）
CASES = [
    # 口语化 / 换词 / 短 query，模拟真实用户提问，增加区分度
    ("试用期最多几个月", "劳动合同法"),
    ("入职没签合同能要双倍工资吗", "劳动合同法"),
    ("被开除能拿多少赔偿", "劳动争议判决书"),
    ("加班不给钱怎么办", "劳动争议判决书"),
    ("欠条到期不还利息怎么算", "民间借贷纠纷判决书"),
    ("朋友借钱不还逾期利息", "民间借贷纠纷判决书"),
    ("打官司几年内有效", "律师实务笔记"),
    ("证据由谁来提供", "律师实务笔记"),
    ("撞伤人要赔哪些费用", "民法典侵权责任编"),
    ("买到假货商家和生产厂家谁赔", "民法典侵权责任编"),
    ("员工干活时伤了人公司要赔吗", "民法典侵权责任编"),
    ("违约金太高能要求减少吗", "民法典合同编"),
    ("签字后合同什么时候算生效", "民法典合同编"),
    ("人从出生到死亡享有什么权利", "rag_test_sample"),
    ("起诉状里面要写什么", "民事起诉状样本"),
]
TOP_K = 5

# Article 级评估集：(query, expected_doc_title, expected_article_no)
# 验证检索能否定位到具体条款（仅在 chunk_by_article=True 且重新入库后有效）
ARTICLE_CASES = [
    ("试用期工资最低不能少于多少", "劳动合同法", "第二十条"),
    ("没签书面合同能要双倍工资吗", "劳动合同法", "第八十二条"),
    ("合同违约金过高可以要求减少吗", "民法典合同编", "第五百八十五条"),
    ("产品缺陷造成损害生产厂家要赔吗", "民法典侵权责任编", "第一千二百零二条"),
    ("工作人员执行工作任务造成他人损害公司赔吗", "民法典侵权责任编", "第一千一百九十一条"),
    ("合同签字盖章后什么时候生效", "民法典合同编", "第五百零二条"),
    ("承诺生效时合同是否成立", "民法典合同编", "第四百八十三条"),
    ("产品有缺陷造成损害，生产者是否赔偿", "民法典侵权责任编", "第一千二百零二条"),
    ("厂家生产的产品致人损害谁负责", "民法典侵权责任编", "第一千二百零二条"),
    ("产品缺陷导致消费者受伤可以找生产厂家吗", "民法典侵权责任编", "第一千二百零二条"),
    ("生产商对缺陷产品承担什么责任", "民法典侵权责任编", "第一千二百零二条"),
]


def main() -> None:
    min_score = getattr(settings, "rerank_min_score", 0.0)
    by_article = getattr(settings, "chunk_by_article", False)
    ranker = getattr(settings, "hybrid_ranker", "rrf")
    print(f"== 评估配置 == ranker={ranker}(rrf_k={settings.rrf_k}) | rerank_min_score={min_score} | 切片={'条款级' if by_article else '字符递归'}")
    print(f"评估集: {len(CASES)} cases, TOP_K={TOP_K}\n")

    hits1 = hits3 = hits5 = 0
    mrr = 0.0
    n = len(CASES)
    for i, (q, exp) in enumerate(CASES, 1):
        res = retrieve.search(q, top_k=TOP_K)
        titles = [h.doc_title for h in res]
        rank = next((idx for idx, t in enumerate(titles, 1) if t == exp), None)
        tag = f"rank={rank}" if rank else "MISS"
        flag = "hit " if rank else "miss"
        top3 = [t[:10] for t in titles[:3]]
        print(f"  [{i:2d}] {flag} q={q[:24]:<24} 期望={exp:<14} {tag}  top3={top3}")
        if rank:
            if rank <= 1:
                hits1 += 1
            if rank <= 3:
                hits3 += 1
            if rank <= 5:
                hits5 += 1
            mrr += 1 / rank

    print("\n--- 汇总 ---")
    print(f"hit@1={hits1}/{n} ({hits1/n:.0%})  hit@3={hits3}/{n} ({hits3/n:.0%})  hit@5={hits5}/{n} ({hits5/n:.0%})  MRR={mrr/n:.3f}")

    # Article 级引用精度评估
    print("\n== Article 级引用精度 ==")
    ah1 = ah3 = ah5 = 0
    amrr = 0.0
    na = len(ARTICLE_CASES)
    for i, (q, exp_doc, exp_art) in enumerate(ARTICLE_CASES, 1):
        res = retrieve.search(q, top_k=TOP_K)
        rank = next(
            (
                idx
                for idx, h in enumerate(res, 1)
                if h.doc_title == exp_doc and h.article_no == exp_art
            ),
            None,
        )
        tag = f"rank={rank}" if rank else "MISS"
        flag = "hit " if rank else "miss"
        top = [(h.doc_title[:6], h.article_no) for h in res[:2]]
        print(f"  [{i:2d}] {flag} q={q[:24]:<24} 期望={exp_doc[:10]}/{exp_art} {tag}  top={top}")
        if rank:
            if rank <= 1:
                ah1 += 1
            if rank <= 3:
                ah3 += 1
            if rank <= 5:
                ah5 += 1
            amrr += 1 / rank

    print("\n--- Article 汇总 ---")
    print(f"article hit@1={ah1}/{na} ({ah1/na:.0%})  hit@3={ah3}/{na} ({ah3/na:.0%})  hit@5={ah5}/{na} ({ah5/na:.0%})  MRR={amrr/na:.3f}")


if __name__ == "__main__":
    main()
