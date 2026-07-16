"""RAG 编排核心：检索链（阶段 3）/ 生成链（阶段 4）。

阶段 3 为纯函数编排（retrieve + rerank），不引入 LangGraph——
状态机编排留到阶段 4 生成链（rewrite/retrieve/rerank/grade/generate/log 节点）再上。
"""
