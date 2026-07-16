# RAG 多模态 VL 实施说明

> 更新日期：2026-07-15  
> 状态：核心代码、数据库迁移、真实百炼调用和端到端图片召回均已完成；修复后完整回归见 [RAG完整回归测试报告](RAG完整回归测试报告_2026-07-15.md)。

## 本次改动清单

| 子系统 | 已实施改动 |
|---|---|
| 数据库 | `kb_document` 增加来源、通用业务关联、案件/卷宗、扩展 JSON、VL 状态、图片统计、`description_summary` 和 `body_markdown`；新增 `kb_document_image` 逐图审计表；迁移已应用至 `a1b2c3d4e5f6` |
| 数据模型 | 同步更新 `law-rag-service` ORM 与 `law-rag-kb` Core Table，RAG 服务可以读写新增字段和图片记录 |
| 解析 | 原来的“返回纯文本”改成 `ParsedDocument`；PDF 保留文本块、页码、内嵌图片，低文本页渲染为扫描页；DOCX 保留段落和图片顺序；增加独立图片格式支持 |
| 清洗 | 新增 Unicode、空白、控制字符、重复页眉页脚清洗，同时保留页码和图片锚点 |
| 图片预筛 | 新增 SHA256 去重、空白/纯色/透明/损坏图片过滤；不按尺寸直接删除法律相关小图 |
| VL | 新增百炼 `qwen3-vl-plus` 客户端、鲁棒 JSON 解析（Unicode 弯引号归一化、花括号配平抽取、裸控制字符转义、尾逗号修复）、`finish_reason` 截断诊断、超时/重试、并发控制、脱敏错误和非思考模式 |
| 法律安全策略 | 仅高置信度 Logo、水印、分隔线过滤；印章、签名、二维码、表格、图示、截图、证据照片及扫描页强制保守保留 |
| MinIO | 原件保持只读；提取图片使用稳定路径写入 `rag-derived/{doc_id}/{source_hash}/`，不创建业务附件记录 |
| 切片/向量 | PDF/DOCX/TXT/MD/图片先统一转 Markdown，第一次结构化切片后才执行 VL；最终 ID 为 `{doc_id}:m:{idx}`、`content_type=markdown`，图片描述/OCR 与正文同块 |
| 检索/问答 | `/search.hits[].text` 与 `/chat.refs[].text` 返回 Markdown；Milvus/聊天日志存 `#img:{id}`，读取时才换预签名 URL |
| 状态接口 | `/documents/{doc_id}` 增加 `vl_status`、图片总数/保留数/过滤数和处理时间；`/health` 增加不计费的 `vl_configured` 检查 |
| Markdown 管线 | `kb_document.body_markdown` 保存最终 Markdown；分类只进 metadata，保留图片的描述/OCR回填 Markdown，超长块二次整形 |
| 批处理 | 批量入库和测试数据脚本新增 PNG/JPG/JPEG/WebP/BMP/TIFF 支持 |
| 测试 | 80/80 单元测试、53/53 完整链路通过；23 个成功文档、198 个 Markdown chunk；10 张图片 VL success（9 保留、1 Logo 过滤） |
| 文档 | 同步更新根 README、RAG 开发计划、测试报告、数据库设计、MinIO 方案、对象规则和整体项目追踪计划 |

主要代码入口：

- `law-rag-kb/app/ingest/document.py`：统一结构化文档与图片分析类型。
- `law-rag-kb/app/ingest/parser.py`：PDF、DOCX、文本和图片解析。
- `law-rag-kb/app/ingest/cleaner.py`：文本清洗。
- `law-rag-kb/app/ingest/image_filter.py`：图片去重与预筛。
- `law-rag-kb/app/ingest/vl.py`：Qwen VL 调用与法律过滤策略。
- `law-rag-kb/app/ingest/markdown_builder.py`：初始 Markdown、draft 切片、VL 回填和最终整形。
- `law-rag-kb/app/rag/describe.py`：LLM 文档级中文摘要生成。
- `law-rag-kb/app/core/storage.py`：MinIO 下载/上传与 `presigned_url` 预签名。
- `law-rag-kb/app/ingest/service.py`：完整入库编排、状态回写与 `build_document_markdown` 渲染。
- `law-rag-service/alembic/versions/9a7e4c2d6f10_add_kb_document_vl_fields.py`：VL 字段迁移。
- `law-rag-service/alembic/versions/f0a1c2d3e4b5_add_kb_document_description_summary.py`：文档摘要列迁移。
- `law-rag-service/alembic/versions/a1b2c3d4e5f6_add_kb_document_body_markdown.py`：最终 Markdown 列迁移。

## 链路

```text
MinIO/正文 → PDF/DOCX/TXT/MD/图片转初始 Markdown → draft 结构化切片
  → 含图片 chunk 调 qwen3-vl-plus → 描述/OCR回填 → 文档概述 → 超长块二次整形
  → BGE-M3 dense+sparse → Milvus Markdown chunk → search/chat 读时解析图片链接
```

- PDF 使用 PyMuPDF 保留文本块、页码和嵌入图片；少文本页面渲染为扫描页图片。
- DOCX 按 XML 顺序保留段落、表格与内嵌图片；TXT 识别章/节/编/条并转标题；原生 MD 保留标题、列表、表格、引用、代码块和缩进；独立图片生成带稳定占位符的初始 Markdown。
- 原件和原图不删除。派生图幂等写入 `rag-derived/{doc_id}/{source_hash}/`。
- 空白、纯色、透明和损坏图片在本地预筛；相同 SHA256 只建立一条图片记录。
- 只有高置信度 Logo、水印和分隔线不参与向量化；印章、签名、二维码、表格、图示、截图、证据照片和扫描页保守保留。
- 不再生成独立图片描述向量；最终统一使用 `{doc_id}:m:{idx}`，图片说明/OCR与附近正文保存在 Markdown chunk，页码、图片 ID 和分类进入 metadata。

## 数据模型

Alembic revision 链尾 `9a7e4c2d6f10` → `f0a1c2d3e4b5` → `a1b2c3d4e5f6`：

- `kb_document` 增加 `source_type`、`biz_type/biz_id`、`case_id`、`dossier_no`、`extra_metadata`、VL 状态、图片统计、`description_summary`，以及持久化最终稳定版本的 `body_markdown`。
- 新增 `kb_document_image`，保存页码、哈希、派生对象地址、分类、描述、筛选原因、模型/提示词版本、token 用量和错误。
- `permission_level` 继续使用原字段；`case_id` 关联 `case_main` 且删除案件时置空。

## 统一 Markdown 切片与渲染

入库时保存最终 `body_markdown`；`GET /documents/{doc_id}/markdown` 读取后现场解析图片链接：

```text
# 文档标题
## 文档概述        ← description_summary（入库时 LLM 生成）
## 正文            ← content_text 或从 MinIO 原件解析；章→##、条→### 轻量结构化
### 第3页图片
![描述前40字](#img:8)
**图片说明：** VL 中文描述
**图片识别文字：** OCR 内容
```

- **处理顺序**：先转初始 Markdown 并形成 draft chunk，VL 只处理含图 chunk；分类保存在图片表，描述/OCR进入最终 Markdown。
- **文档概述**：VL 后复用文本 LLM 基于正文、图片说明和 OCR 生成；失败降级为 NULL，不阻断入库。
- **图片链接**：PostgreSQL/Milvus/聊天日志只存 `#img:{id}`；`/documents`、`/search`、`/chat` 返回时批量换为预签名 URL。
- **降级**：过滤/失败图片从最终 Markdown 删除；混合文档仍入库正文，纯图片无有效内容时失败。
- **安全注意**：预签名 URL 在有效期内任何人持链接可取图；RAG 服务端现已在生成 URL 前强制校验服务身份、活动用户和案件/文档权限，并把默认有效期缩短为 300 秒。生产仍必须通过平台登录网关代理，不能把内部服务 Token 交给浏览器。

## 配置与安全

VL 默认使用 `qwen3-vl-plus` 和百炼 OpenAI 兼容端点。`VL_API_KEY` 可独立配置；为空时复用本地环境中的 `LLM_API_KEY`，不会写入仓库或日志。图片以 Base64/HTTPS 提交，只附标题、页码和有限附近正文。

重要配置见 `law-rag-kb/.env.example`：超时 60 秒、供应商重试 3 次、并发 4、过滤阈值 0.90、单图最大输出 token 2048（防长描述 JSON 截断）、提示词版本 `v1`。

## 状态与降级

- 无图片文档：文本正常入库，`vl_status=success`。
- 单图失败：文本仍入库，VL 汇总为 `partial` 或 `failed`。
- 纯图片/扫描文档没有任何有效图片描述：入库失败且旧 Milvus 向量不先删除。
- 强制重入库先完成 VL 和 Embedding，再替换 Milvus 旧向量；图片表通过文档 ID + 图片哈希幂等更新。

## 验证

- 自动化：80/80 通过；覆盖原生 MD 结构与裸法条 metadata、编/章/节/条上下文、DOCX 表格/图片顺序、先切片后 VL、图片 metadata 隔离、描述/OCR回填、超长图片块整形、稳定链接安全和 Docker `/ready` 语义。
- 原阶段 3–7 回归：53/53 通过。
- 真实 `qwen3-vl-plus`：流程图（`doc_id=21`）识别为 `diagram`、`keep_for_rag=true`、`confidence=0.98`，并完整提取"签订合同→履行义务→发生争议→收集证据→协商或诉讼"五阶段；页眉律所标识（`doc_id=19`）识别为 `decorative_logo`、`keep_for_rag=false`、`confidence=0.98`。
- 真实端到端：`doc_id=21` 强制入库成功，Milvus 为 3 个 `21:m:*` Markdown chunk；图片 chunk 内含 `#img:8`、VL 描述与 OCR，`/search` 和 `/chat.refs[].text` 返回预签名链接，聊天日志不含 URL。
- VL 故障降级：`doc_id=22` 在 VL API 不可用时仍 `status=success`（`chunk_count=1`、`vl_status=failed`），错误信息脱敏为 `VL provider request failed (APITimeoutError)`，不泄露 Key/Base64/正文。
- 文档 Markdown 渲染：`doc_id=21` force 重入库后生成 `21:m:0000..0002`；`GET /documents/21/markdown` 返回标题、概述、正文、图片说明/OCR及预签名原图，持久层仍只含 `#img:8`。
- 最新运行态：23 个 success 文档全部有 `body_markdown`；Milvus 198/198 为 Markdown，旧 `:t:`/`:i:` 为 0；PostgreSQL、Milvus和聊天日志均无持久化 `X-Amz-*`。
- 30 张真实人工标注集涉及案件隐私，不提交仓库；评估入口为 `scripts/eval_vl.py`，受控数据准备说明见 `tests/fixtures/vl_eval/README.md`。

## 已知问题与修复（2026-07-14）

- **`qwen3-vl-plus` 偶发返回非法 JSON（`VL returned invalid JSON (JSONDecodeError)`）**：直连真实模型定位到根因——该模型非确定性地用 Unicode 弯引号 `“ ”`（U+201C/U+201D，偶有 ‘ ’ « » ＂）包裹 JSON 的个别键，替代 ASCII 双引号 `"`，标准 `json.loads` 只认 U+0022，于是报 `Expecting property name enclosed in double quotes`。`finish_reason=stop`（非截断）、`content` 为字符串（非数组），故问题在 JSON 正文。修复在 [vl.py](../law-rag-kb/app/ingest/vl.py)：`_normalize_json_text` 单次结构感知行走，按"开引号→配对闭引号集合"识别字符串边界，**只把 Unicode 引号分隔符归一化为 ASCII `"`，保留正文里的弯引号**，同时转义串内裸控制字符、删尾逗号；`_extract_json_object` 用花括号配平取代 `find/rfind`；`_request` 回传 `finish_reason`，失败错误为脱敏元数据。修复后 `doc_id=20/21` 连续多次真实调用全部成功。
- **测试图中文变成 `????`**：Windows PowerShell 5.1 管道把含中文 here-string 编码丢失；属测试材料生成问题，非 VL 识别错误。改用 ASCII + Unicode 转义重新生成测试图后，OCR 与检索均正确。

## 尚未完成或需要业务配合

- 代码和评估工具已经具备，但仓库没有30张脱敏真实业务图片；正式准确率门槛需在业务方提供受控数据后执行。
- `case_id`、`permission_level` 的强制授权已接入 `/search`、`/chat` 和文档读取入口；授权范围由 PostgreSQL 计算成显式 `doc_id` 列表后再查询 Milvus。平台侧登录/JWT 网关仍需联调。
- `/documents/{id}/markdown` 只有授权用户可读取，预签名图片链接默认 300 秒有效；链接在有效期内仍属于 bearer capability，调用方不得记录、转发或持久化。
- 旧二进制 `.doc` 仍不支持；PDF 扫描页已通过 VL 覆盖。
- 当前继续沿用同步入库；大量图片文档的后台任务、限流、成本看板和并发压测仍属于生产化工作。
- 先前在对话中出现过明文 API Key，必须轮换后更新本地环境变量，不能写入代码或 Markdown。
