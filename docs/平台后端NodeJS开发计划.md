# 平台后端 NodeJS 开发计划

> 最后更新：2026-07-22
> 状态：开发中；NestJS/Prisma 骨架、附件、案件材料、RAG 基础网关、公共知识库上传、任意层级分类管理、软删除与回收站已落地
> 范围：仅覆盖**一体化平台（OA 业务）后端**。知识库 / RAG 后端已独立为 Python 服务（`law-rag-kb/`），见 [RAG开发计划](RAG开发计划.md)。

## 1. 背景与决策

一体化平台（OA 业务）后端采用 **NodeJS 应用层**。知识库 / RAG 算法不在本计划范围，由独立 Python 服务承担；平台后端负责用户登录、业务权限、案件与附件，并作为前端访问 RAG 的认证网关和代理。当前 RAG 使用 Python 纯函数编排与本地 BGE 模型，未来复杂 Agent/多步状态再评估 LangGraph。决策与选型：

| 维度 | 决策 |
|---|---|
| 框架 | NestJS（模块化 / DI / 装饰器，企业级结构化） |
| ORM | Prisma（schema-first，类型安全，可 introspect 现有 83 表） |
| 语言 | TypeScript |
| Python 资产 | `law-rag-service` 保留为**数据库维护工具**（init_db / seed_dict_data / Alembic 迁移），不重写、不废弃 |
| 数据库迁移管理 | 仍归 Alembic（Python），Node 端**不接手 DDL**，只用 Prisma 映射现有表 |
| 数据库 / MinIO | 不变，Node 直接连现有 PostgreSQL（`oa` schema）与 MinIO bucket `law-firm-files` |
| Milvus | 由知识库 Python 服务（`law-rag-kb`）使用，Node 一体化平台**不直连 Milvus** |

**为什么不重写迁移**：Alembic 已有 32 个迁移、485 索引、653 字典项，schema 稳定且 init_db 校验全绿。重写迁移风险高、收益低。Python 留作 DB 工具，Node 专注业务应用层，知识库另起 Python 服务，三者边界清晰。

## 2. 架构边界

```
┌───────────────────────────────────────┐
│  law-platform-api/   NodeJS 一体化平台      │
│  NestJS + Prisma + TypeScript          │
│  业务 API / service / MinIO 附件绑定   │
└──────────────┬────────────────────────┘
               │ 读写业务数据
               ▼
     ┌─────────────────┐    ┌────────────────────┐
     │  PostgreSQL      │    │  MinIO             │
     │  oa schema       │    │  bucket            │
     │  80表 / 9视图    │    │  law-firm-files    │
     └────────▲─────────┘    └────────▲───────────┘
              │                       │
┌─────────────┴───────────────────────┴──────────────┐
│  law-rag-kb/   Python 知识库 RAG（独立服务）        │
│  FastAPI + pymilvus + FlagEmbedding                 │
│  文档解析 / Embedding(BGE-M3) / Reranker /          │
│  Milvus 检索 / Qwen3.7 Plus 生成；POST /search、/chat│
└──────────────┬─────────────────────────────────────┘
               │ 读文档原件 + 向量
               ▼
     ┌─────────────────┐
     │  Milvus 19530    │  bucket a-bucket（与业务 MinIO 共用同一实例）
     └─────────────────┘

┌───────────────────────────────────────────────────┐
│  law-rag-service/   Python DB 维护工具（保留）     │
│  Alembic 迁移 / init_db.py / seed_dict_data.py /   │
│  Excel 同步 / tmp_*_flow_test.py                   │
│  职责：DDL / 字典种子 / DB 校验                    │
└───────────────────────────────────────────────────┘
```

**关键边界规则**：
- DDL（建表/改字段/外键/索引）只发生在 Python 侧（Alembic + Excel 四同步）。Node 侧**禁止**用 Prisma migrate 改 schema。
- Node 侧 schema 变更响应：Python Alembic 升级 DB 后，Node 侧跑 `prisma db pull` 同步 `schema.prisma`。
- 字典数据只由 Python `seed_dict_data.py` 灌入。Node 侧只读字典。
- Milvus 与 RAG 算法链路全部在 `law-rag-kb`（Python）；Node 平台不直连 Milvus，只负责认证、业务权限和 RAG HTTP 代理。

## 3. Node 项目结构（`law-platform-api/`）

```
law-platform-api/
├── package.json
├── tsconfig.json
├── nest-cli.json
├── .env                      # 复用 DB/MinIO 配置
├── prisma/
│   └── schema.prisma         # 由 prisma db pull 从现有 oa schema 生成
├── src/
│   ├── main.ts               # NestJS bootstrap
│   ├── app.module.ts
│   ├── core/
│   │   ├── config/           # @nestjs/config 读 .env
│   │   ├── prisma/           # PrismaModule + PrismaService（封装 client）
│   │   └── minio/            # MinioModule + MinioService（对应 Python minio_service）
│   ├── modules/              # 业务模块，每模块 controller + service + dto
│   │   ├── attachments/      # 首个模块：对应 attachment_service
│   │   ├── cases/
│   │   ├── finance/
│   │   ├── marketing/
│   │   └── ...
│   └── common/               # 过滤器、拦截器、响应格式、装饰器
└── test/                     # e2e（对应 Python verify_attachment_service）
```

> 注：Node 侧不再含 `milvus/` 模块——向量检索归 `law-rag-kb`（Python）。

## 4. Prisma 接手现有 DB

```bash
# 初始化
npx prisma init

# 从现有 PostgreSQL oa schema 反向生成 schema.prisma（不改 DB）
npx prisma db pull --schema=prisma/schema.prisma
# 生成 client
npx prisma generate
```

`schema.prisma` 关键配置：
```prisma
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")  // postgresql://law_rag_user:...@localhost:5432/law_rag
  schemas  = ["oa"]
}

generator client {
  provider = "prisma-client-js"
  previewFeatures = ["multiSchema"]
}
```

**已知限制**：
- Prisma 对**视图**支持有限：9 个统计视图（`v_*`）不生成模型，需用 `prisma.$queryRaw` 裸查询。
- Prisma 对**外键命名**、枚举映射可能与 Alembic 建的有差异，`db pull` 后需人工校对 `schema.prisma`（尤其 `@@schema`、`@@map`、字段 `@map`）。
- `oa.sys_dict_item` 的字典值（字符串码 vs 数字字典）技术债沿用 Python 侧现状，Node 读取时按实际值处理。

## 5. Service 重写优先级

按「已有 Python 参照 + 价值高」排序：

| 顺序 | 模块 | Python 参照 | 说明 |
|---|---|---|---|
| 1 | `attachments` | `app/services/attachment_service.py` | **首个迁移**：MinIO + sys_attachment 闭环，逻辑清晰，验证 Node+Prisma+MinIO 链路 |
| 2 | `cases` | `tmp_case_management_flow_test.py` | 案管核心：建案/分案/材料/进度/结案 |
| 3 | `finance` | `tmp_finance_flow_test.py` | 回款/开票/退费 |
| 4 | `marketing` | `tmp_marketing_flow_test.py` | 线索/电邀/签约 |
| 5 | `legal` / `admin` / `operation` | 对应 tmp_*.py | 律师/行政绩效/运营 |

> RAG / 知识库检索（原计划的 `search` 模块）已从 Node 剥离，归独立 Python 服务 `law-rag-kb/`，见 [RAG开发计划](RAG开发计划.md)。

## 6. API 路由规划

NestJS controller，RESTful，按业务模块：

```
POST   /attachments/upload          # 上传 → 写 sys_attachment + MinIO
GET    /attachments/:id/download
GET    /attachments/:id/presigned-url
DELETE /attachments/:id
POST   /attachments/:id/bind        # 写 sys_attachment_relation

POST   /api/rag/search              # 代理 FastAPI /search
POST   /api/rag/chat                # 代理 FastAPI /chat
GET    /api/rag/categories          # 递归分类树（含路径、深度、文档计数）
POST   /api/rag/categories          # 新增根/子分类
PATCH  /api/rag/categories/:id      # 改名、别名、移动、排序、归档/敏感/启停
DELETE /api/rag/categories/:id      # 安全停用（不物理删除）
GET    /api/rag/documents           # 文档列表，支持 category_id/status/keyword/分页
PATCH  /api/rag/documents/:id/title # 改标题（只更 PostgreSQL，不重新入库）
PATCH  /api/rag/documents/:id/category  # 迁移已有文档分类
POST   /api/rag/documents/batch-move    # 批量改分类（≤100）
POST   /api/rag/documents/batch-delete  # 纯软删 → 进回收站（保留原件/图片/向量）
POST   /api/rag/documents/batch-restore # 从回收站恢复（校验原件/图片/向量齐全）
POST   /api/rag/documents/batch-purge   # 永久删除（清理 MinIO/Milvus/派生图片）
GET    /api/rag/documents/trash     # 回收站列表（分页/搜索/分类筛选/按删除时间）
 
GET    /cases                       # 案件台账（v_case_management_ledger）
POST   /cases                       # 建案
GET    /cases/:id
PATCH  /cases/:id/status            # 状态流转
...（各业务模块类似）
```

> 注：`/search`、`/chat`（RAG）及知识分类仍由独立 Python 服务 `law-rag-kb/` 提供（默认 :8000）；Node 已通过 `/api/rag/search`、`/api/rag/chat`、`/api/rag/categories` 提供基础代理。当前尚无登录态用户上下文，生产身份注入仍待完成。

## 7. 知识库 / RAG 边界（独立 Python 服务）

知识库 / RAG 后端独立为 `law-rag-kb/`（Python），**不归属 Node 一体化平台**。主要原因是 BGE-M3 dense+sparse Embedding、bge-reranker-v2-m3 和 Milvus hybrid 检索均依赖成熟的 Python 推理生态；当前编排为纯函数模块，未安装 LangChain/LangGraph。

| 维度 | 归属 | 技术 |
|---|---|---|
| 业务 API（OA / 案件 / 财务 / 附件） | Node `law-platform-api` | NestJS + Prisma |
| 文档向量化 / Embedding / Reranker | Python `law-rag-kb` | FlagEmbedding（BGE-M3 + bge-reranker-v2-m3） |
| 向量检索（Milvus） | Python `law-rag-kb` | pymilvus 连 `localhost:19530` |
| RAG 编排 / Agent | Python `law-rag-kb` | 当前纯函数编排；LangGraph 为未来 Agent 预留 |
| LLM 生成 | Python `law-rag-kb` | 阿里云百炼 `qwen3.7-plus`（OpenAI 兼容、非思考模式） |
| 内部 RAG 接口 | Python `law-rag-kb` | FastAPI `POST /search`、`POST /chat`（:8000，均已验证） |
| 前端 RAG 网关 | Node `law-platform-api` | 基础代理、字段白名单、服务端 Token、超时和安全错误映射已完成；登录态与用户 ID 注入待完成 |

两服务共用同一套基础设施（PostgreSQL `oa` schema、MinIO `law-firm-files`、Milvus），由根级 `docker-compose.yml` 统一编排。平台与知识库的协作：平台把法律文档附件写入 MinIO，知识库服务读取、解析、向量化入库。

## 8. 分阶段开发步骤

| 阶段 | 状态 | 目标 | 产出 |
|---|---|---|---|
| 0 | ✅ | 规划与选型 | 本文档 |
| 1 | ✅ | Node 项目骨架 | `law-platform-api/` + NestJS + Prisma schema + 配置与 PG/MinIO |
| 2 | ✅ | 基础设施 service | `MinioService` + `AttachmentService` + 单元/e2e 测试 |
| 3 | ✅ | 首个 API | `AttachmentsController`（上传/下载/预签名/绑定）+ DTO；案件材料 API 已加入 |
| 4 | ⏳ | 业务模块 | cases/finance/marketing/legal/admin/operation 按优先级开发 + 流程测试转 Node |
| 5 | ⏳ | 统计视图 | 9 个 `v_*` 视图的 `$queryRaw` 封装 + 台账 API |
| 6A | ✅ | RAG 基础网关 | `/api/rag/search`、`/api/rag/chat`、DTO 校验、内部 Token、超时和安全错误映射 |
| 6C | ✅ | 公共知识库上传 | 文件校验、SHA-256 去重、MinIO/DB 登记、入库/状态/Markdown 代理 |
| 6D | ✅ | 任意层级分类管理 | 分类树 CRUD、安全移动/停用、同级排序、文档改分类、父级筛选含后代 |
| 6E | ✅ | 软删除与回收站 | 普通删除纯软删、`batch-purge` 永久清理、`/trash` 列表、`batch-restore` 原子恢复与 `verify-restore`、`file_hash` 软删占用；迁移 `f1a2b3c4d5e6` |
| 6B | ⏳ | 认证与正式权限 | 登录/JWT、用户上下文、权限守卫和 `X-RAG-User-Id` 注入 |

> RAG 算法服务由独立 Python 项目 `law-rag-kb/` 承担，见 [RAG开发计划](RAG开发计划.md)。平台不重复实现 RAG；阶段 6A 基础代理和 6C 公共上传编排已经完成，阶段 6B 继续补认证和用户权限上下文。

## 9. 验证

每阶段对应验证：
- **阶段 2**：Node `AttachmentService` 端到端（上传→写 sys_attachment→下载一致→预签名→relation），与 Python `verify_attachment_service.py` 行为对齐。
- **阶段 3**：`curl POST /attachments/upload` 走通 HTTP 链路。
- **阶段 4**：每个业务模块迁移后，对照 Python `tmp_*_flow_test.py` 跑等价 Node 流程测试。
- **阶段 6A/6C/6D**：RAG 网关覆盖参数校验、字段白名单、上游错误脱敏、上传格式、SHA-256 去重、事务和 MinIO 补偿；分类接口覆盖同级重名、循环移动、系统分类保护、安全停用和文档迁移。2026-07-17 平台总基线为单元 43/43、HTTP E2E 15/15，ESLint 与 build 通过。
- **全程**：Python `init_db.py` 仍负责 DB 校验（83 表/207 外键/485 索引/145 字典类别/653 项），Node 不碰这些数字。

## 10. 风险与待定项

| 项 | 风险 | 应对 |
|---|---|---|
| Prisma view 支持 | 9 个视图不能自动映射 | 用 `$queryRaw`，封装到 `src/core/views/` |
| schema 双边同步 | Alembic 改 DB 后 Node schema.prisma 滞后 | 流程固化：Python 改 schema → `prisma db pull` 同步 Node |
| 字典取值技术债 | biz_type/storage_type 字典数字 vs 实际字符串码 | Node 按实际值处理，不在 Node 侧修字典 |
| 测试脚本迁移 | tmp_*.py 流程测试是否转 Node | 业务模块迁移时逐个转 Node e2e，Python tmp 保留作 DB 层回归 |
| 目录命名 | 已固定为 `law-platform-api/` | 与 `law-rag-kb/` 的职责边界清晰 |

> 原「Embedding 方案」风险项已随 RAG 移出 Node 范围而消除——Embedding 由 Python 知识库服务内嵌 BGE-M3 承担。

## 11. 不迁移的内容（明确保留 Python）

- `alembic/`（全部迁移与 schema 管理）
- `scripts/init_db.py` / `seed_dict_data.py`（DB 初始化与字典种子）
- `scripts/generate_models_from_excel.py` / `sync_excel_*.py`（Excel 模型生成与同步）
- `scripts/verify_attachment_service.py`（Python 侧回归基线）
- `tmp_*_flow_test.py`（DB 层流程回归）
- `app/models/`（SQLAlchemy 模型，作为 Prisma schema 的参照源）

> 知识库 / RAG 相关 Python 代码位于独立目录 `law-rag-kb/`，不在 `law-rag-service/` 内（后者专注 DB 维护）。
