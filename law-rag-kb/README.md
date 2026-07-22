# law-rag-kb 知识库 RAG 服务（Python）

法律 RAG 项目的**知识库 / AI 后端**，基于 Python 构建，负责文档向量化、检索与问答生成。

> 当前进度：**阶段 0–8、统一 Markdown 多模态链路、RAG 服务端权限/生产安全基线和知识库软删除与回收站（`/documents/verify-restore`、`/documents/batch-delete`）均已完成**。PDF/DOCX/TXT/MD/图片先转 Markdown，第一次结构化切片后仅对含图 chunk 调用 `qwen3-vl-plus`，再将有检索价值的描述/OCR回填；文本生成使用 `qwen3.7-plus`。已修复 DOCX 图片抽取的命名空间 xpath 崩溃（改 Clark 记法）与 chunker 空分隔符导致的 `text.split("")` 崩溃。后续重点是平台登录网关联调、旧 DOC、真实图片评估集、异步入库与长稳优化。

功能完整验收见 [RAG完整回归测试报告](../docs/RAG完整回归测试报告_2026-07-15.md)；后续安全专项见 [RAG权限与生产安全处理报告](../docs/RAG权限与生产安全处理报告_2026-07-15.md)：当前自动化为 115 passed + 5 subtests，真实生产模式的 401/404、文档隔离、案件拒绝、非 root 容器和启动 fail-closed 均已验证。

## 定位（双后端架构）

本项目后端为双语言双服务结构：

| 目录 | 语言 | 职责 |
|---|---|---|
| `law-platform-api/` | NodeJS（NestJS） | 一体化平台业务 API（OA / 案件 / 财务 / 附件等） |
| `law-rag-kb/`（本目录） | Python（FastAPI） | 知识库 RAG：文档解析、Embedding、检索、Reranker、生成 |
| `law-rag-service/` | Python | DB 维护工具（Alembic 迁移 / 字典 / 校验），不承载应用层 |

开发环境可仅绑定本机直接调试；生产环境必须由 Node/API Gateway 验证用户登录态并代理调用，本服务不对浏览器或公网直接暴露。

## 技术栈

| 层级 | 选型 |
|---|---|
| Web 框架 | FastAPI + Uvicorn |
| 向量检索 | Milvus 2.6（`pymilvus.MilvusClient` 连 `localhost:19530`） |
| Embedding | BGE-M3（dense + sparse + hybrid），FlagEmbedding 1.2.10 |
| Reranker | bge-reranker-v2-m3（阶段 3 启用） |
| 对象存储 | MinIO（读法律文档原件，bucket `law-firm-files`） |
| 关系库 | PostgreSQL（只读/回写 `oa` schema 的 `kb_document` / `sys_attachment`，Core Table 声明） |
| 文档解析 | PyMuPDF / python-docx / Pillow（PDF/DOCX/TXT/MD/常见图片） |
| 图片理解 | 阿里云百炼 `qwen3-vl-plus`，分类、OCR/描述和过滤 |
| LLM | 阿里云百炼 `qwen3.7-plus`，OpenAI 兼容 Chat Completions，默认关闭深度思考 |

## 复用的基础设施（与平台共用，不新建）

- **PostgreSQL** `localhost:5432`（`oa` schema）—— 知识库表 `kb_document` / `sys_attachment` 等已落地
- **MinIO** `localhost:9000`（bucket `law-firm-files`）—— 业务文件 + Milvus 共用同一实例
- **Milvus** `localhost:19530`（向量库，collection `kb_chunks`）

三者均由根级 `docker-compose.yml` 统一编排，启动方式见根 [README.md](../README.md)。

## 目录结构

```text
law-rag-kb/
├── app/
│   ├── main.py              # FastAPI 入口（lifespan 释放 PG engine）
│   ├── api/
│   │   ├── health.py        # /health 三连检（PG/MinIO/Milvus）
│   │   ├── documents.py     # 入库、状态与 GET /documents/{id}/markdown
│   │   ├── search.py        # POST /search（hybrid 召回 + reranker 精排）
│   │   └── chat.py          # POST /chat（检索→生成→引用，写 ai_chat_log）
│   ├── core/
│   │   ├── config.py        # pydantic-settings 配置
│   │   ├── security.py      # 服务 Token、数据库活动用户与角色身份
│   │   ├── authorization.py # 文档/部门/所有者/案件统一授权策略
│   │   ├── constants.py     # EmbeddingStatus 枚举
│   │   ├── database.py      # SQLAlchemy engine + search_path=oa
│   │   ├── milvus_client.py # MilvusClient 单例 + ensure_collection（建 kb_chunks）
│   │   ├── minio_client.py  # Minio 单例
│   │   └── storage.py       # MinIO 原件下载 + rag-derived 派生图片幂等写入
│   ├── ingest/              # 入库链
│   │   ├── document.py      # 有序内容节点、图片与分析结果等统一中间类型
│   │   ├── parser.py        # PDF/DOCX/TXT/MD/图片 → 有序节点+图片+页码
│   │   ├── markdown_builder.py # 初始 Markdown、draft 切片、VL 回填与最终整形
│   │   ├── cleaner.py       # Unicode/空白/重复页眉页脚清洗
│   │   ├── image_filter.py  # 图片哈希去重与空白/纯色/透明预筛
│   │   ├── vl.py            # qwen3-vl-plus 分类与描述
│   │   ├── chunker.py       # 旧管线兼容切片与 Markdown 辅助投影
│   │   ├── embedding.py     # BGE-M3 单例 + encode_batch（dense+sparse）
│   │   └── service.py       # 编排器：状态机 + 幂等（先算后删）+ 异常回写
│   ├── rag/                 # hybrid 检索、reranker、prompt 与真实 LLM 生成
│   │   ├── retrieve.py      # hybrid 召回（dense+sparse+RRFRanker）+ rerank 编排
│   │   ├── reranker.py      # FlagReranker 单例 + rerank（bge-reranker-v2-m3）
│   │   ├── prompt.py        # 法律域 prompt 组装 + knowledge_refs 引用
│   │   ├── markdown.py      # 稳定图片占位解析、读时预签名与纯文本投影
│   │   ├── category_resolver.py  # 从 PostgreSQL 批量解析分类路径与敏感标记
│   │   ├── llm.py           # LLM 抽象层（当前 Qwen3.7 Plus / stub / ollama）
│   │   └── chat.py          # 问答编排：检索→生成→引用→写 ai_chat_log
│   └── models/
│       └── tables.py        # kb_document / sys_attachment Core Table（不 import law-rag-service ORM）
├── scripts/
│   ├── batch_ingest.py      # test_files 批量幂等入库/强制重建
│   ├── eval_retrieval.py    # 文档级 + 法条级 Hit@K/MRR
│   ├── benchmark_search.py  # 已启动 /search 的正确性与延迟基准
│   ├── benchmark_concurrency.py # 1/5/10 路并发正确性与延迟基准
│   └── seed_test_doc.py     # 造测试数据：上传 test_files 到 MinIO + 插 kb_document/sys_attachment
├── tests/                   # unittest：切片边界、误判防护、API 契约与引用字段
├── requirements.txt
├── .env.example
└── README.md
```

## 对外接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | PG/MinIO/Milvus 连检 + `vl_configured`（不产生外部调用） |
| GET | `/ready` | Docker 就绪检查；基础设施或本地模型目录不可用时返回 503 |
| POST | `/documents/{doc_id}/ingest?force=false` | 转初始 Markdown → draft 切片 → 含图块 VL → 回填/整形 → BGE-M3 → Milvus |
| GET | `/documents/{doc_id}` | `embedding_status`、`vl_status`、图片统计和实时切片数 |
| GET | `/documents/{doc_id}/markdown?source_id=` | 合并或按来源返回最终 Markdown |
| GET | `/documents/{doc_id}/chunks?...&source_id=` | 合并或按来源分页返回 Chunk，不返回向量 |
| POST | `/documents/{staging_id}/promote-source` | 平台内部使用：安全追加/替换一个来源 |
| POST | `/documents/rebuild-sources` | 平台内部使用：全部来源成功后原子重建 |
| POST | `/search` | 自然语言检索：query → BGE-M3 编码 → hybrid 召回（dense+sparse）→ bge-reranker 精排 → 返回片段+来源 |
| POST | `/chat` | RAG 问答：检索（复用 `/search`）→ prompt 组装 → LLM 生成 → 引用标注 → 写 `ai_chat_log` → 返回答案+引用 |

## 认证与权限

开发默认 `AUTH_ENABLED=false`，保持本地脚本兼容。生产必须设置 `APP_ENV=production`、`AUTH_ENABLED=true` 和至少 32 字符的随机 `RAG_SERVICE_TOKEN`；否则应用拒绝启动。`/health` 保持开放，`/ready` 会返回认证配置状态。

读取接口要求两个请求头：

```http
Authorization: Bearer <internal-service-token>
X-RAG-User-Id: <authenticated-sys_user-id>
```

服务 Token 只能由上游网关持有；RAG 会用数据库重新验证用户、员工、有效角色、部门和案件成员关系。`public/internal/department/private/case` 权限均在 Milvus 检索前收窄；未知权限默认拒绝，案件文档不能通过误标 `public` 绕过。容器同时采用非 root、只读根文件系统、无 capabilities 和禁止提权配置。完整矩阵、真实验证和启用清单见 [权限与生产安全处理报告](../docs/RAG权限与生产安全处理报告_2026-07-15.md)。

`/search.hits[].text` 与 `/chat.refs[].text` 均返回完整 Markdown chunk。多源文档使用 `{doc_id}:s:{source_id}:m:{source_chunk_idx}`，metadata保存来源 ID、标题、原文件名和来源内序号；历史单文件 `{doc_id}:m:{idx}` 在下次全来源强制重建时转换。分类只在 metadata，新 Chunk 保存 `category_id` 与当时的 `category_path` 快照，检索/问答引用阶段通过 `category_resolver.py` 从 PostgreSQL 批量解析最新分类路径；分类改名、移动或文档改分类后无需重建向量。图片通过 chunk 内 `#img:{id}` 建立关系，API 响应阶段才生成预签名 URL。

入库链状态机：`pending → processing → success`（失败 `failed`，不支持文件类型/缺 object_key `skipped`），回写到 `kb_document.embedding_status` 与 `sys_attachment.ai_index_status`。

> 当前本地 `.env` 已启用 `LLM_PROVIDER=openai` + 阿里云百炼 `qwen3.7-plus`。密钥只保存在被 `.gitignore` 排除的本地 `.env`，不得写入 README、日志或提交记录。需要离线验证时可临时切回 `LLM_PROVIDER=stub`。

## 阶段 6 历史基线

- 该节记录阶段 6 当时的历史基线，不代表当前运行态。
- 当时 7 份业务样本文档强制重建成功，测试数据为 11 个已索引文档、60 个 Milvus chunk。
- 法规采用“一条法条至少一个独立 chunk”，超长条文拆分后仍继承相同 `article_no` / `chapter`，避免多法条合并导致引用错号。
- 当时 `scripts/eval_retrieval.py` 为文档级 15/15、法条级 7/7，两组 MRR 均为 1.000。
- 当时 CPU 环境 mean 约 5.4s；该数值已被下方当前回归基线替代。
- 当时 `python -m unittest discover -s tests -v` 为 25 个测试。

## 当前回归基线（2026-07-20）

- 原功能回归为 Python 80/80、在线阶段测试 53/53；权限专项加入后为 93 passed + 5 subtests；任意层级分类树与分类元数据解析加入后为 104 passed + 5 subtests；知识库软删除与回收站加入后当前为 115 passed + 5 subtests。
- 文档级检索 Hit@1/3/5=15/15，法条级 Hit@1/3/5=11/11，两组 MRR 均为 1.000。
- 顺序基准 15/15：mean=3.126s、P50=2.829s、P95=4.757s。
- 5 路并发 5/5：wall=17.328s、mean=10.055s；10 路并发 10/10：wall=34.622s、mean=20.979s。
- 23 个成功文档、198 个 Milvus Markdown chunk；旧 `:t:`/`:i:` 与持久化预签名 URL 均为 0。
- 历史文档 3、5、6、8、18 已逐个安全重建，全库“节作为 chapter”归零；清理后文档级 15/15、法条级 11/11。证据见 [历史数据清理报告](../docs/RAG历史数据清理报告_2026-07-15.md)。

## 多模态 VL 验证结果

- Alembic `9a7e4c2d6f10` 已应用，新增案件/卷宗字段及 `kb_document_image`。
- 外部 `qwen3-vl-plus` 真实验证：流程图判为 `diagram` 并保留；页眉标识判为 `decorative_logo` 并过滤，置信度均为 0.95。
- 旧独立图片向量曾以 `doc_id=17` 完成幂等召回验证；该 `:i:` 设计现已由统一 `:m:` Markdown chunk 取代。
- 当前运行态复验：23 篇成功文档均有 `body_markdown`；Milvus 198 个 chunk 全部为 `content_type=markdown`，旧 `:t:`/`:i:` ID 与持久化 URL 均为 0；10 张图片 VL success，9 张保留、1 张 Logo 过滤。
- 完整设计、状态与安全说明见 [RAG多模态VL实施说明](../docs/RAG多模态VL实施说明.md)。

## 阶段 7：真实 LLM 接入结果

- 百炼北京按量 OpenAI 兼容端点与 `qwen3.7-plus` 已完成最小调用验证。
- `/chat` 端到端验证通过：检索第1202/1203条 → Qwen 生成答案 → 返回 `[1]`/`[2]` 引用 → 写 `ai_chat_log`，首次完整请求约14秒。
- 无依据拒答验证通过：针对知识库未收录的盗窃罪量刑问题，模型明确返回“依据不足”，未编造刑法条文。
- 配置了90秒超时、2次重试、1200最大输出 token、temperature=0.2，并关闭 Qwen 深度思考以控制延迟与费用。
- 外部供应商超时、限流或无效响应统一映射为脱敏的 HTTP 502，不向调用方泄露密钥或底层请求信息。

## ⚠️ 关键环境约束（务必遵守）

1. **`FlagEmbedding==1.2.10` + `transformers==4.44.2`** 实测兼容。FlagEmbedding 1.4.0 重构后与 transformers 4.x（dtype 报错）/5.x（return_colbert 报错）**均不兼容**——不要升级这两个包。
2. **BGE-M3 模型本机无法从 HuggingFace / hf-mirror 下载**（hf-mirror 的 LFS CDN 域名不存在 + `huggingface_hub` 1.x 对 307 重定向不兼容）。改用 **modelscope** 下载到本地：
   ```bash
   pip install modelscope
   python -c "from modelscope import snapshot_download; print(snapshot_download('BAAI/bge-m3', allow_patterns=['*.json','*.model','*.txt','pytorch_model.bin','sparse_linear.pt']))"
   ```
   下载到 `~/.cache/modelscope/models/BAAI--bge-m3/snapshots/master`，`.env` 的 `EMBEDDING_MODEL` 指向该本地路径。
3. **bge-reranker-v2-m3（阶段 3 检索链）同样从 modelscope 下载**（HF 同样不可达）：
   ```bash
   python -c "from modelscope import snapshot_download; print(snapshot_download('BAAI/bge-reranker-v2-m3'))"
   ```
   `.env` 的 `RERANKER_MODEL` 指向 `~/.cache/modelscope/models/BAAI--bge-reranker-v2-m3/snapshots/master`。
4. 服务必须带 **`HF_HUB_OFFLINE=1`** 启动（本地模型不查网络）。
5. **Windows PowerShell 5.1 不要把含中文的 here-string 直接管道到 `python -`**。PowerShell 5.1 的原生管道默认可能使用 ASCII `$OutputEncoding`，导致中文在进入 Python 前变成 `?`。使用项目包装器，它会临时切换 stdin/stdout 为无 BOM UTF-8，并在结束后恢复原会话设置：

   ```powershell
   cd D:\law-rag-project\law-rag-kb
   $code = @'
   text = "产品缺陷造成损害，生产者是否承担责任？"
   print(text)
   '@
   .\scripts\Invoke-PythonUtf8.ps1 -Code $code

   # 也支持 PowerShell 对象管道；此时进入原生 Python 前由包装器统一转成 UTF-8
   $code | .\scripts\Invoke-PythonUtf8.ps1
   ```

   不含中文的一行命令仍可直接使用 `python -c`；较长的正式测试优先保存为 UTF-8 `.py` 文件。

## Docker 一键启动（推荐）

RAG API 已加入根级 `docker-compose.yml`。两个本地模型通过只读目录挂载复用，不写入镜像；数据库迁移由一次性 `db-migrate` 容器先执行。

在根 `.env` 配置模型路径：

```dotenv
BGE_M3_HOST_PATH=C:/Users/17962/.cache/modelscope/models/BAAI--bge-m3/snapshots/master
RERANKER_HOST_PATH=C:/Users/17962/.cache/modelscope/models/BAAI--bge-reranker-v2-m3/snapshots/master
```

首次构建与后续启动：

```powershell
cd D:\law-rag-project
docker compose up -d --build
docker compose ps
docker compose logs -f rag-api

# 后续无需重新构建
docker compose up -d
```

`rag-api` 只绑定 `127.0.0.1:8000`，并使用容器服务名连接 `postgres`、`minio` 和 `standalone`。`/ready` 不加载模型、不调用百炼；BGE-M3/Reranker 在第一次检索时按需加载。Docker 启动不会自动入库文档，仍需调用 `/documents/{id}/ingest` 或批处理脚本。

当前根 `.env` 仍是开发兼容模式，`/ready.authentication=disabled`。正式切换生产前先完成 Node/API Gateway 登录态代理，再按安全报告注入 Token；不要把内部 Token 放入浏览器。

若要随电脑启动，请在 Docker Desktop 中开启登录时启动。Qwen3.7 Plus 与 Qwen3-VL 是云端模型，容器只运行调用方。

## 本地 Python 启动（开发调试）

```bash
cd law-rag-kb
.venv\Scripts\activate
pip install -r requirements.txt   # 首次
# 模型需先用 modelscope 下载到本地（见上节），并在 .env 设 EMBEDDING_MODEL 指向本地路径
$env:HF_HUB_OFFLINE=1             # PowerShell；bash 用 export HF_HUB_OFFLINE=1
uvicorn app.main:app --reload --port 8000
```

验证入库（需先 `docker compose up -d` 起 PG/MinIO/Milvus）：

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
python scripts/seed_test_doc.py test_files/rag_test_sample.txt   # 造测试数据，打印 doc_id
curl -X POST http://localhost:8000/documents/<doc_id>/ingest
curl http://localhost:8000/documents/<doc_id>
# 检索链（阶段 3）
curl -X POST http://localhost:8000/search -H 'Content-Type: application/json' \
  -d '{"query":"借款合同纠纷的诉讼时效","top_k":3}'
# 问答链（当前调用阿里云百炼 qwen3.7-plus，返回真实答案与引用）
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"question":"自然人的民事权利能力从何时开始？","top_k":3}'
```
