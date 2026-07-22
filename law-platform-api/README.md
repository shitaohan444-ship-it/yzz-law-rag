# law-platform-api 平台业务后端

律师事务所综合平台的 NodeJS 业务后端，使用 NestJS、Prisma 和 TypeScript。它面向前端提供 OA、案件、附件、客户、财务和权限等业务 API，并作为前端访问 `law-rag-kb` 的受控网关。

## 职责边界

| 目录 | 职责 |
|---|---|
| `law-platform-api/` | 平台登录、用户与组织、案件、附件、业务权限、RAG 网关 |
| `law-rag-kb/` | FastAPI 文档解析、向量化、Milvus 检索、Reranker、Qwen 问答 |
| `law-rag-service/` | Alembic 数据库迁移、字典种子、Excel 同步和 DB 校验 |

平台后端不加载 BGE 模型、不直连 Milvus，也不实现文档切片或 LLM 编排。生产环境中，浏览器只访问平台后端；平台验证登录态后，再把内部服务 Token 和已认证用户 ID 传给 FastAPI RAG 服务。

```text
浏览器 / 前端
      ↓
law-platform-api（登录、角色、部门、案件权限）
      ↓ HTTP + 内部 Token + 用户 ID
law-rag-kb（入库、检索、问答、引用）
      ↓
PostgreSQL + MinIO + Milvus + Qwen
```

## 当前功能

- 案件材料创建、查询、更新和文件替换
- 附件上传、绑定和对象存储访问
- Prisma 访问 PostgreSQL `oa` schema
- MinIO `law-firm-files` bucket 访问封装
- DTO 参数校验和统一错误处理
- `POST /api/rag/search` 法条检索网关
- `POST /api/rag/chat` 知识问答网关
- 公共知识库上传、列表、状态、Markdown、Chunk 分页和自动入库代理
- 公共知识库批量导入复用单文件接口；文档标题可独立修改且不触发重新入库
- 公共知识库多源文件追加、源文件管理与单来源安全替换
- 数据库驱动的任意层级知识分类树：新增、改名、移动、排序、安全停用、文档计数与历史文档改分类
- 分类父节点筛选自动包含全部后代；敏感标记仅用于分类提示，所有入库资料自动面向当前可信局域网检索
- 知识库软删除与独立回收站：普通删除纯软删（保留原件/图片/向量可恢复），`POST /documents/batch-purge` 永久清理，`GET /documents/trash` 列表，`POST /documents/batch-restore` 经 `verify-restore` 原子恢复；`file_hash` 按 `status` 占用，回收站同文件阻止重复上传
- 批量改分类 `batch-move`、文档列表按 `category_id`/`status`/`keyword` 过滤分页
- 全部来源原子强制重建：任一来源失败时保留重建前的完整知识库
- 上传登记与 RAG 入库分阶段耗时持久化（仅保留最近一次）
- 文档最后上传时间及每个源文件上传时间聚合返回
- SHA-256 文件去重、50MB/格式校验及 MinIO/数据库失败补偿
- RAG 超时、断线、无效响应与安全错误映射
- 单元测试与真实 PostgreSQL/MinIO HTTP E2E

尚待开发：登录/JWT、用户与角色、部门、完整案件业务、客户、合同、财务，以及登录态用户身份到 RAG 权限上下文的联调。

## 目录结构

```text
law-platform-api/
├── src/
│   ├── main.ts                    # NestJS 启动入口
│   ├── app.module.ts              # 根模块
│   ├── common/                    # 通用常量、错误与参数解析
│   ├── core/
│   │   ├── config/                # 环境变量校验
│   │   ├── prisma/                # PrismaModule / PrismaService
│   │   └── minio/                 # MinioModule / MinioService
│   └── modules/
│       ├── attachments/            # 附件模块
│       ├── case-materials/         # 案件材料模块
│       ├── knowledge-documents/    # 公共知识库上传、多源文件、分类树与入库编排
│       └── rag/                    # FastAPI 检索/问答/文档受控代理
├── prisma/schema.prisma            # 由现有 oa schema 映射
├── test/                            # HTTP E2E
├── package.json
└── pnpm-lock.yaml
```

## 运行环境

- Node.js 22.x（以 `.nvmrc` 和 `package.json#engines` 为准）
- pnpm 10.x
- PostgreSQL 16
- MinIO

平台 API 已加入项目根 `docker-compose.yml`，与数据库、MinIO、Milvus、FastAPI 和前端一起启动。容器内监听 `0.0.0.0:3000`，宿主机仍只绑定 `127.0.0.1:3000`，不会直接暴露到局域网。

## Docker 一键启动（推荐）

```powershell
cd D:\law-rag-project
docker compose up -d --build
docker compose ps
```

容器使用 Docker 内部地址 `postgres:5432`、`minio:9000` 和 `rag-api:8000`。完成首次构建后，只要 Docker Desktop 开启“登录时启动”且没有手工停止容器，平台 API 会通过 `restart: unless-stopped` 自动恢复。

## 本地开发启动（可选）

需要 NestJS 热更新时，先停止平台 API 和前端容器以释放端口：

```powershell
cd D:\law-rag-project
docker compose stop platform-web platform-api

cd D:\law-rag-project\law-platform-api
pnpm install
pnpm run prisma:generate
pnpm run start:dev
```

RAG 网关配置写入本目录 `.env`；可复制 `.env.example`，主要变量如下：

```dotenv
RAG_API_BASE_URL=http://127.0.0.1:8000
RAG_API_TIMEOUT_MS=120000
RAG_INGEST_TIMEOUT_MS=900000
RAG_SERVICE_TOKEN=
```

本地开发时 `HOST` 默认是 `127.0.0.1`，由同机 Vite 代理访问，不要为了局域网前端而改成 `0.0.0.0`；Docker 会在容器内部单独覆盖为 `0.0.0.0`。开发模式关闭 FastAPI 鉴权时，`RAG_SERVICE_TOKEN` 可以留空。启用 FastAPI 鉴权后，令牌只保存在平台后端或根 Compose 环境中，禁止写入前端 `VITE_` 变量。当前局域网验收版没有登录功能，因此 FastAPI 应保持开发兼容模式；生产启用鉴权前必须先补齐平台用户身份注入。

其他启动命令：

```powershell
pnpm run start       # 普通启动
pnpm run start:debug # 调试并监听文件变化
pnpm run build
pnpm run start:prod  # 运行 dist/main
```

## 验证

```powershell
pnpm exec eslint "{src,apps,libs,test}/**/*.ts"
pnpm run prisma:generate
pnpm run build
pnpm run test -- --runInBand
pnpm run test:e2e -- --runInBand
```

RAG 网关测试额外覆盖请求白名单、内部令牌、参数校验、超时、断线、无效 JSON 和上游安全错误。2026-07-16 当前基线：单元测试 40/40、HTTP E2E 15/15，ESLint 与 build 通过；知识文档列表允许 `page_size` 1–1000，前端提供 5、10、20、50、100、500、1000 七档选择。上传测试还覆盖文件签名、SHA-256 去重、事务登记、MinIO 补偿、上传 timing 持久化、来源追加提升及 Chunk 响应不含向量字段。

2026-07-17 分类功能完成后的当前基线为单元测试 43/43、HTTP E2E 15/15，ESLint 与 build 通过。新增 `GET/POST /api/rag/categories`、`PATCH/DELETE /api/rag/categories/{id}` 和 `PATCH /api/rag/documents/{id}/category`；同级重名、循环移动、系统分类修改、有关联文档或子节点的停用均返回安全错误。分类变更只更新 PostgreSQL，不触发 FastAPI 入库、Embedding 或 Qwen。

多源文件接口为 `GET/POST /api/rag/documents/{id}/sources` 和 `PUT /api/rag/documents/{id}/sources/{sourceId}/file`。追加或替换先使用隐藏 staging 附件/文档完成真实解析、Embedding 和 Milvus 写入，成功后才提升到原 `doc_id`；失败会清理 staging，其他来源及原 Chunk 继续可用。相同文件、跨文档重复文件和同一文档并发操作返回安全 `409`。`POST /api/rag/documents/{id}/ingest?force=true` 对全部有效来源执行原子重建。

Markdown 与 Chunk 查询支持可选 `source_id`；不传时合并全部有效来源，传入后只返回指定来源。Chunk 默认每页 20、最大 100，响应包含来源标签但不包含向量。`oa.kb_document_source` 由 Alembic `d8e9f0a1b2c3` 创建并回填历史主文件；平台通过参数化原生 SQL 访问，不使用 Prisma Migrate。

标题修改使用 `PATCH /api/rag/documents/{id}/title`，请求体为 `{ "title": "新标题" }`。标题去除首尾空格后为 1–255 字符，只更新活动文档的 PostgreSQL 标题；附件、源文件、Markdown、Chunk、向量和最后上传时间不变。文档摘要返回 `last_uploaded_at`，源文件返回 `uploaded_at`：优先使用成功上传计时的 `completed_at`，历史数据回退到来源创建时间，文档值取全部有效来源的最大值。

2026-07-20 新增能力后的单元测试基线为 51/51，ESLint 与 build 通过；测试覆盖标题去空格和长度校验、标题修改不调用入库，以及来源/文档上传时间序列化。

2026-07-20 修复分类计数与文档列表的旧数据兼容问题：列表不再按附件 `biz_type` 排除早期 `document` 类型的活动知识库文档，而是以 `kb_document` 为归属依据。分类停用被文档阻止时会返回真实剩余数量。真实分类 #4 的计数与列表均返回 2 份，当前平台单元测试为 56/56，ESLint 与 build 通过。

2026-07-20 完成知识库软删除与回收站：`batchDelete` 改纯软删（响应 `{deleted,mode:'soft',artifacts_retained:true}`），新增 `POST /documents/batch-purge`、`GET /documents/trash`、`POST /documents/batch-restore`（经 `verify-restore` 校验原件/图片/向量齐全后原子恢复）；去重在软删冲突时返回 `409 SOFT_DELETED_DUPLICATE`，`purged` 后释放哈希位。当前单元测试 67/67、HTTP E2E 15/15，ESLint 与 build 通过；部署与验收细节见 [软删除与回收站部署说明](../docs/软删除与回收站部署说明_2026-07-20.md)。

完整实现与真实浏览器验收记录见 [简单 RAG 前端与局域网测试报告](../docs/简单RAG前端与局域网测试报告_2026-07-15.md)。
公共知识库上传实现见 [公共知识库上传第一版实施报告](../docs/公共知识库上传第一版实施报告_2026-07-16.md)。

## 数据库变更规则

- 禁止在平台侧使用 Prisma Migrate 修改生产 schema。
- 表、字段、外键和索引由 `law-rag-service/alembic/` 维护。
- 数据库升级后，在本目录运行 `pnpm exec prisma db pull` 同步 `prisma/schema.prisma`。
- 字典种子继续由 `law-rag-service/scripts/seed_dict_data.py` 维护。

分类表和文档分类外键由 Alembic `e9f0a1b2c3d4` 创建并迁移历史数据；Prisma Schema 只同步映射 `kb_category` 与 `kb_document.category_id`，不负责 DDL。

## 下一步

1. 实现登录、JWT/Session 和当前用户上下文。
2. 实现角色、部门、案件成员等业务授权。
3. 由平台后端注入已认证用户 ID；浏览器继续不得持有内部 Token。
4. 完成平台权限与 FastAPI `public/internal/department/private/case` 权限联调。
