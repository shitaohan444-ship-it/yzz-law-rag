# RAG 开发计划（知识库 Python 服务）

> 最后更新：2026-07-15
> 状态：阶段 0–8 核心链路、多模态 VL、RAG 服务端权限与生产安全基线已完成。平台登录网关联调、旧 DOC、异步化和大规模人工评估继续推进。
> 关联：[平台后端NodeJS开发计划](平台后端NodeJS开发计划.md)（一体化平台）、[数据库设计](数据库设计.md)、[MinIO对象规则](MinIO对象规则.md)

## 1. 背景与定位

知识库 / RAG 后端**独立为 Python 服务 `law-rag-kb`**，与 NodeJS 一体化平台并列。原因：

- Embedding、稀疏向量和 reranker 依赖成熟的 Python 模型生态；当前链路采用可测试的纯函数编排，后续多轮 Agent/工具调用再评估 LangGraph。
- Embedding / Reranker（BGE-M3 / bge-reranker）需本地 Python 推理（sentence-transformers / FlagEmbedding），Node 原生支持差（尤其 sparse vector）。
- 检索-生成链路自成体系，与 OA 业务 CRUD 解耦，独立服务便于迭代与扩展（Agent、多轮、工具调用）。

**对外**：开发环境可通过本机端口调试；生产由 Node/API Gateway 验证登录态后代理，RAG 仅接受内部服务 Token 和经数据库复核的用户上下文。

## 2. 技术栈

| 层级 | 选型 | 说明 |
|---|---|---|
| Web 框架 | FastAPI + Uvicorn | 轻量、异步、自带 OpenAPI 文档 |
| RAG 编排 | Python 纯函数模块 | 当前实现 ingest / retrieve / rerank / prompt / llm / chat；未引入 LangChain |
| Agent / 多步流程 | LangGraph（预留） | 当前未安装；未来需要查询改写、grade、工具调用或多轮状态时再引入 |
| 向量检索 | pymilvus | 连 `localhost:19530`，BGE-M3 dense + sparse 混合检索 |
| Embedding | BGE-M3（sentence-transformers / FlagEmbedding） | dense(1024) + sparse，支持 hybrid search |
| Reranker | bge-reranker-v2-m3 | 对召回片段二次精排 |
| 对象存储 | minio（Python SDK） | 读 `law-firm-files` bucket 的法律文档原件 |
| 关系库 | psycopg + SQLAlchemy | 读写 `oa.kb_document`、`kb_document_image`、附件状态与问答日志 |
| 文档解析 | PyMuPDF / python-docx / Pillow | PDF 文本块/图片/扫描页、DOCX、TXT/MD、常见图片 |
| VL 图片理解 | 阿里云百炼 `qwen3-vl-plus` | 初始 Markdown 第一次切片后，仅对含图 chunk 分类/描述/OCR，OpenAI 兼容接口 |
| LLM 生成 | 阿里云百炼 `qwen3.7-plus` | OpenAI 兼容 Chat Completions；关闭深度思考；Stub/Ollama 保留 |

## 3. 服务结构与接口

目录结构（`law-rag-kb/`）：

```text
law-rag-kb/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── api/                 # 路由：/search /chat /documents
│   ├── core/                # 配置（pydantic-settings）、依赖注入、日志
│   ├── rag/                 # 当前纯函数检索/生成编排与 Markdown 读时解析
│   │   ├── retrieve.py      # hybrid 检索 + rerank
│   │   ├── reranker.py      # bge-reranker-v2-m3
│   │   ├── prompt.py        # 法律域 prompt + 引用编号
│   │   ├── llm.py           # Stub / OpenAI 兼容 / Ollama 抽象层
│   │   └── chat.py          # 检索 → 生成 → 引用 → 日志
│   ├── ingest/              # 有序解析、Markdown 构建/两次整形、VL、Embedding、入库编排
│   └── models/              # 知识库表 SQLAlchemy 模型（或复用 law-rag-service 的）
├── requirements.txt
├── .env.example
└── README.md
```

对外接口（规划）：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/search` | 自然语言检索，返回相关片段 + 来源（文档/页码/条款） |
| POST | `/chat` | RAG 问答，检索 + LLM 生成，带引用 |
| POST | `/documents/{doc_id}/ingest` | 按 `kb_document` 触发统一 Markdown 转换、draft 切片、含图块 VL、回填与向量化 |
| GET | `/documents/{id}` | 查询文档入库状态、切片数等 |
| GET | `/documents/{id}/markdown` | 读取最终 `body_markdown`，请求时解析稳定图片占位符 |
| GET | `/health` | 健康检查 |

## 4. 数据流与存储设计

### 4.1 文档来源

法律文档原件存于 MinIO bucket `law-firm-files`（由一体化平台附件流程上传，`sys_attachment` 记录 `object_key`）。知识库服务按 `kb_document` 登记的文档读取原件、解析、向量化。

### 4.2 关系库（PostgreSQL `oa` schema，已落地）

复用并扩展知识库表：
- `kb_document` —— 文档登记、案件/卷宗通用关联、文本/VL 入库状态、图片统计、`description_summary` 与最终 `body_markdown`
- `kb_document_image` —— 逐图哈希、页码、派生对象、分类、描述、筛选和模型审计
- `ai_chat_log` / `ai_analysis_record` / `ai_analysis_review` —— 问答日志与分析结果
- `ai_transcription_record` —— 录音转写（如有）

### 4.3 向量库（Milvus）

collection 设计（`kb_chunks`，已落地，见 `app/core/milvus_client.py`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | VARCHAR(128) PK | 统一 Markdown chunk：`{doc_id}:m:{idx}` |
| `doc_id` | INT64 | 关联 `kb_document.id`（hybrid_search `expr` 过滤用） |
| `chunk_idx` | INT16 | 文档内切片序号（稳定，参与 PK） |
| `source` | VARCHAR(100) | legal_category（法规/案例/案件材料/工作资料） |
| `chunk_text` | VARCHAR(65535) | 最终 Markdown chunk；图片使用稳定 `#img:{id}`，不保存预签名 URL |
| `dense` | FLOAT_VECTOR(1024) | BGE-M3 dense |
| `sparse` | SPARSE_FLOAT_VECTOR | BGE-M3 sparse |
| `meta` | JSON | `content_type=markdown`、条款/章节、页码、图片ID/分类、案件/卷宗及权限元数据 |

索引：`dense` 用 HNSW(M=16, efConstruction=200)+COSINE；`sparse` 用 SPARSE_INVERTED_INDEX+IP；`hybrid_search` 融合（默认 RRFRanker(k=60) / WeightedRanker 可配）。

## 5. RAG 核心流程

### 5.1 入库链（Ingest）

```
MinIO 原件 → PDF/DOCX/TXT/MD/图片转初始 Markdown → draft 结构化切片
  → 含图片 chunk 执行 qwen3-vl-plus → 描述/OCR回填 → 概述/超长块整形
  → BGE-M3 Embedding(dense+sparse) → 写 Milvus Markdown chunk
  → 更新 kb_document 入库状态 / 切片数
```

切片策略：第一次按 Markdown 块级结构识别标题、法条、段落、列表、引用、表格、代码块和图片节点；每个 chunk 携带文档标题，不跨法条合并，图片尽量保留邻近上下文且 overlap 不重复图片。VL 回填后只对超长 draft chunk 二次拆分，保留标题、章节/法条和图片引用；最终顺序与完整 Markdown 一致。

### 5.2 查询链（当前纯函数编排）

```
用户问题 → [查询改写/扩展] → 并行召回(dense + sparse hybrid) → rerank(bge-reranker)
  → 取 top-K 片段 → 组装 prompt → LLM 生成 → 引用标注 → 返回
```

未来引入 LangGraph 时的节点建议：
1. `rewrite` —— 查询归一化 / 多查询扩展（可选）
2. `retrieve` —— hybrid 召回（dense + sparse）
3. `rerank` —— bge-reranker 精排
4. `grade` —— 相关性判断（可选，过滤无关片段）
5. `generate` —— LLM 生成 + 引用
6. `log` —— 写 `ai_chat_log`

## 6. 与一体化平台的协作

- **文档上传**：平台侧（Node）负责法律文档上传到 MinIO + 写 `sys_attachment` / `kb_document`。
- **向量化触发**：平台调知识库服务 `POST /documents/{doc_id}/ingest`（或知识库定时扫描 `kb_document` 待入库项）。
- **检索/问答**：生产由平台网关转发 `/search` `/chat`，浏览器不持有 RAG 服务 Token。
- **权限**：RAG 已按活动用户、有效角色、部门、所有者和案件成员关系强制过滤；平台仍需完成登录/JWT 守卫并传递可信用户 ID。

## 7. 里程碑

| 阶段 | 目标 | 产出 |
|---|---|---|
| 0 | 骨架 | `law-rag-kb/` 目录 + README + requirements + .env.example ✅ |
| 1 | 服务骨架 | FastAPI 启动 + 配置 + 连通 PG/MinIO/Milvus + `/health` ✅ |
| 2 | 入库链 | 单文档（PDF/DOCX/TXT）解析 → 切片 → BGE-M3 → Milvus 入库，`kb_document` 状态回写 ✅（MilvusClient + `kb_chunks` collection；BGE-M3 经 modelscope 本地加载，见 [memory/rag-kb-stage2-ingest](../C:/Users/17962/.claude/projects/d--law-rag-project/memory/rag-kb-stage2-ingest.md)）|
| 3 | 检索链 | hybrid 召回 + bge-reranker + `/search` 接口，返回片段与来源 ✅（dense+sparse + RRFRanker(k=60) 融合；reranker 用 FlagEmbedding.FlagReranker 同栈，不引 sentence-transformers；民法典查询精准命中）|
| 4 | 生成链 | ✅ 纯函数编排 retrieve→prompt→LLM→引用→`ai_chat_log`；当前已从 Stub 切换为阿里云百炼 `qwen3.7-plus`，Stub/Ollama 保留作开发回退 |
| 5 | 批量入库 | 批量 ingest `test_files/` 法律文档，`ai_chat_log` 记录问答 ✅（`scripts/batch_ingest.py` 按 object_key 幂等；7 文档 19 chunk 入库；多文档检索精准命中劳动合同法/判决书/实务笔记；`/chat` 累积写 `ai_chat_log`）|
| 6 | 核心调优 | ✅ 法条独立切片与 `article_no/chapter`；chapter 仅由“章”赋值；`rerank_min_score`；RRF/weighted 可配置；文档级 15/15、法条级 11/11；顺序与 1/5/10 路性能脚本 |
| 7 | 生产化 | 🚧 `qwen3.7-plus`、引用/拒答、脱敏 502、检索计时、CPU 分批、服务认证、文档/案件授权、容器加固和生产 fail-closed 已完成；平台登录代理、旧 DOC、扩大生成评估集、异步入库、集中监控、长稳及 GPU/MPS 评估待续 |
| 8 | 多模态 VL | ✅ `qwen3-vl-plus`；统一 Markdown 转换与 draft 切片后 VL；分类进 metadata、描述/OCR回填；`:m:` chunk、`body_markdown`、读时预签名；80/80 单元测试、53/53 链路回归，10 张真实图片 VL success |

## 8. 环境与启动

```bash
cd law-rag-kb
python -m venv .venv
.venv\Scripts\activate           # Windows
pip install -r requirements.txt
copy .env.example .env           # 按需修改（模型路径、LLM key 等）
uvicorn app.main:app --reload --port 8000
```

基础设施（PostgreSQL / MinIO / Milvus）由根级 `docker-compose.yml` 统一提供，本服务不单独起容器。

## 9. 待决策项

| 项 | 备选 | 备注 |
|---|---|---|
| LLM 生成 | 外部 API / 本地推理 | ✅ 已选阿里云百炼 `qwen3.7-plus`，北京按量 OpenAI 兼容端点；非思考模式；Stub/Ollama 作为开发回退 |
| 模型部署设备 | CPU / GPU / Apple Silicon MPS | ✅ 已定 CPU（BGE-M3 经 FlagEmbedding 1.2.10 本地推理，modelscope 下载；Mac 迁移后评估 MPS） |
| 切片粒度 | 条款级 / 固定 token / 滑窗 | ✅ 阶段 6：法规一条法条至少一个独立 chunk，超长法条子块继承条号；非结构文本按中文标点递归切片 |
| hybrid 融合 | RRF / weighted 配比 | ✅ 默认 RRFRanker(k=60)；代码支持 WeightedRanker 与 dense/sparse 权重配置，扩大评估集后继续对比 |
| reranker 实现 | FlagReranker / sentence-transformers CrossEncoder | ✅ 阶段 3 已定 FlagReranker（复用 FlagEmbedding 1.2.10，避免与 transformers 4.44.2 冲突） |
| 入库触发 | 平台主动调用 / 知识库定时扫描 | ✅ 阶段 2 同步 `POST /documents/{id}/ingest`；阶段 5 `scripts/batch_ingest.py` 批量脚本（按 object_key 幂等，子目录映射 legal_category）；定时扫描留阶段 6+ |
