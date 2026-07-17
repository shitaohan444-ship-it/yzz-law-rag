# 法律 RAG 知识库（Law RAG）

本地法律文档检索增强生成（RAG）项目，基于 **React 前端 + NodeJS/Python 双后端** + PostgreSQL + Milvus + MinIO 构建；PDF/DOCX/TXT/MD/图片统一转为 Markdown，先按 Markdown 结构切片，再由 `qwen3-vl-plus` 为含图片切片补充描述与 OCR。

- **一体化平台后端**用 NodeJS（NestJS）：OA / 案件 / 财务等业务 API。
- **知识库 RAG 后端**用 Python（FastAPI + pymilvus + FlagEmbedding）：文档向量化、混合检索、精排和问答生成；当前采用纯函数编排，LangGraph 留作后续 Agent/多步流程。
- **数据库维护工具**用 Python（Alembic）：schema 迁移 / 字典 / 校验。

## 项目定位

用于管理、解析、向量化和检索法律相关文档，支持通过自然语言问答从法律法规、判决案例、案件材料等资料中检索答案。

## 项目与目录职责

本仓库是一套完整系统，不是多个互不相关的项目。需要开发的代码分为 **一个前端 + 两个运行服务 + 一个数据库维护工具**：

| 目录 | 类型 | 职责 | 是否直接对外提供服务 |
|---|---|---|---|
| `law-platform-web/` | React 前端 | 法条检索、RAG 问答与引用展示；通过平台网关访问知识库 | 是，局域网测试端口 5173 |
| `law-platform-api/` | NodeJS 业务后端 | OA、案件材料、附件、MinIO 与平台业务 API | 是 |
| `law-rag-kb/` | Python AI/RAG 后端 | 文档解析、向量化、Milvus 检索、Reranker 和问答生成 | 是，但生产环境应由平台网关代理 |
| `law-rag-service/` | Python DB 维护工具 | Alembic 迁移、字典种子、Excel 同步和数据库校验 | 否 |
| `milvus-standalone/` | 基础设施数据 | Milvus/etcd 持久化数据卷 | 否 |
| `models/` | 本地模型材料 | 历史模型下载目录；实际运行模型路径以根 `.env` 为准 | 否 |
| `docs/` | 项目文档 | 架构、数据库设计、开发计划、测试和修复报告 | 否 |
| `test_files/` | 测试输入 | 用于入库、解析、VL 和检索测试的法律文档 | 否 |
| `test-evidence/` | 测试输出 | 环境、基础设施、pytest 和快速回归的验收证据 | 否 |
| `.github/` | CI 配置 | GitHub Actions，目前验证 Node API | 否 |
| `.claude/` | 开发工具配置 | AI 编程工具的项目级与本机权限设置 | 否 |

### 完整目录图

```text
law-rag-project/
├── README.md                       # 本文件：项目总览
├── docker-compose.yml              # PostgreSQL + MinIO + Milvus + 迁移 + RAG API 唯一入口
├── .env                            # 本机真实配置与密钥，不提交
├── .env.example                    # 不含真实密钥的根级配置示例
├── .github/workflows/              # GitHub Actions CI
├── .claude/                        # AI 开发工具配置
├── docs/                           # 设计文档、计划、报告和数据库设计 Excel
├── law-platform-web/               # React + Vite 法律检索与问答前端
│   ├── src/                        # 页面、API 客户端、类型与组件测试
│   └── e2e/                        # Playwright 模拟/真实 RAG 浏览器测试
├── law-platform-api/               # NestJS + Prisma + TypeScript 业务后端
│   ├── src/
│   │   ├── common/                 # 通用常量、错误与参数解析
│   │   ├── core/config/            # 环境变量校验
│   │   ├── core/minio/             # MinIO 访问封装
│   │   ├── core/prisma/            # PostgreSQL/Prisma 连接
│   │   └── modules/                # attachments、case-materials 等业务模块
│   ├── prisma/                     # schema.prisma
│   ├── test/                       # HTTP/E2E 测试
│   ├── dist/                       # 编译产物，可重新生成
│   └── node_modules/               # pnpm 依赖，可重新安装
├── law-rag-kb/                     # FastAPI 知识库与 AI 后端
│   ├── app/
│   │   ├── api/                    # health/documents/search/chat 接口
│   │   ├── core/                   # 配置、认证授权、PG/MinIO/Milvus 客户端
│   │   ├── ingest/                 # 解析、Markdown、VL、切片和向量化入库链
│   │   ├── rag/                    # 混合检索、精排、Prompt、LLM 和引用
│   │   └── models/                 # RAG 使用的数据库表声明
│   ├── scripts/                    # 批量入库、质量评估和性能基准
│   ├── tests/                      # Python 自动化测试与 VL 评估说明
│   └── .venv/                      # 本地 Python 虚拟环境，可重建
├── law-rag-service/                # DB 维护工具，不承载应用 API
│   ├── alembic/
│   │   ├── versions/               # 数据库迁移链
│   │   └── views/                  # PostgreSQL 统计视图 SQL
│   ├── app/
│   │   ├── core/                   # DB 维护配置和连接
│   │   ├── models/                 # SQLAlchemy 模型，Prisma schema 的参照源
│   │   └── services/               # Python 版附件/MinIO 参考实现
│   ├── scripts/                    # init_db、字典种子、Excel 同步与校验
│   └── data/
│       ├── postgres/               # PostgreSQL 真实持久化数据，禁止随意删除
│       └── minio/                  # 业务附件和 Milvus bucket，禁止随意删除
├── milvus-standalone/
│   └── volumes/
│       ├── etcd/                   # Milvus 元数据，禁止随意删除
│       ├── milvus/                 # 向量索引与运行数据，禁止随意删除
│       └── minio/                  # 合并前的遗留 MinIO 数据卷，当前不再挂载
├── models/
│   └── bge-m3/                     # 历史 hf-mirror 模型仓库；当前不含完整模型权重
├── test_files/
│   ├── 判决案例/                   # 判决书样本
│   ├── 工作资料/                   # 律师实务资料
│   ├── 案件材料/                   # 起诉状等案件文件
│   └── 法律法规/                   # 法律法规样本
└── test-evidence/
    ├── phase-01-environment/       # 运行时、依赖、配置和模型检查
    ├── phase-02-infrastructure/    # Docker、PG、MinIO、etcd、Milvus 检查
    ├── phase-03-python-tests/      # pytest/JUnit 输出
    └── quick-test/                 # 快速回归结果
```

### 生成物与持久化数据

- 可重新生成：`law-platform-api/dist/`、`law-platform-api/node_modules/`、各项目的 `.venv/`、`.pytest_cache/` 和 `__pycache__/`。
- 测试材料：`test_files/` 是输入样本，`test-evidence/` 是测试运行后的输出证据，两者不要混淆。
- 重要持久化数据：`law-rag-service/data/postgres/`、`law-rag-service/data/minio/`、`milvus-standalone/volumes/etcd/` 和 `milvus-standalone/volumes/milvus/`，删除会导致数据库、附件或向量数据丢失。
- `milvus-standalone/volumes/minio/` 是 MinIO 合并前的遗留目录，当前根级 compose 不再挂载；清理前仍应先确认或备份。
- 根 `models/bge-m3/` 当前没有完整权重，Docker 实际挂载位置由 `.env` 的 `BGE_M3_HOST_PATH` 与 `RERANKER_HOST_PATH` 决定。

## 核心技术栈

| 层级 | 技术 |
|---|---|
| 前端 | React + TypeScript + Vite（法条检索、知识问答、引用展示） |
| 一体化平台后端 | Node.js 22 LTS + NestJS + TypeScript（OA 业务 API / service / 附件 / RAG 网关） |
| 知识库 RAG 后端 | Python + FastAPI + pymilvus + FlagEmbedding（当前纯函数编排；LangGraph 预留） |
| 应用 ORM（平台侧） | Prisma（introspect 现有 `oa` schema） |
| DB 维护工具 | Python + SQLAlchemy 2 + Alembic（schema 迁移 / 字典种子 / DB 校验，保留不迁） |
| 关系型数据库 | PostgreSQL 16 |
| 向量数据库 | Milvus 2.6.19（知识库服务用 pymilvus 连接） |
| 对象存储 | MinIO（业务附件 + Milvus 内部存储 共用同一实例） |
| 文档解析 | 知识库服务：PyMuPDF / python-docx / Pillow；平台侧 Node：mammoth / pdf-parse |
| Embedding / Reranker | BGE-M3（dense + sparse + hybrid）+ bge-reranker-v2-m3，知识库服务内嵌本地推理 |
| LLM 生成 | 阿里云百炼 `qwen3.7-plus`（OpenAI 兼容 API，非思考模式）；Stub/Ollama 仍可切换 |

## MinIO（单一实例，业务 + Milvus 共用）

项目只有**一套 MinIO**：业务附件与 Milvus 向量库内部存储共用同一实例，各用各的 bucket，互不干扰。

| 维度 | 说明 |
|---|---|
| 容器 | `law-rag-minio` |
| API | `localhost:9000` |
| Console | `localhost:9001`（minioadmin / minioadmin123） |
| 业务 bucket | `law-firm-files`（法律文档附件，平台与知识库服务读写） |
| Milvus bucket | `a-bucket`（Milvus 默认 bucket，启动时自建，请勿手动操作） |

Milvus 通过 docker 网络内 service 名 `minio:9000` 连接此实例，凭据由根级 `.env` 注入。详细规则见 [MinIO对象规则](docs/MinIO对象规则.md)。

## 快速启动

1. 首次构建并启动整套系统（PostgreSQL、MinIO、Milvus、数据库迁移、RAG API、平台 API 和前端）：

   ```powershell
   cd D:\law-rag-project
   docker compose up -d --build
   ```

   启动前确认根 `.env` 中 `BGE_M3_HOST_PATH` 和 `RERANKER_HOST_PATH` 指向已下载的 ModelScope 模型。迁移容器会自动执行 `alembic upgrade head`，不再需要手工初始化 schema。

2. 日常启动、停止、查看状态和日志：

   ```powershell
   docker compose up -d
   docker compose stop
   docker compose ps
   docker compose logs -f platform-web platform-api rag-api
   ```

3. 验证后端和前端：

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/ready
   Invoke-RestMethod http://127.0.0.1:8000/health
   Invoke-WebRequest http://127.0.0.1:5173 -UseBasicParsing
   ```

   `/ready` 只有在 PostgreSQL、MinIO、Milvus和两个本地模型目录全部可用时才返回 200；模型在第一次检索时按需加载。Docker 不会自动扫描或入库 pending 文档。

4. 本机使用 `http://127.0.0.1:5173`；同一局域网的电脑或手机使用 `http://服务器局域网IP:5173`。前端容器只把 `/api` 转发到 Docker 内部的 `platform-api:3000`，浏览器不会直连 FastAPI。局域网只需按需放行 Windows 防火墙 TCP 5173，不要开放 3000、8000、5432、6333 或 9000。

完成一次 `docker compose up -d --build` 后，开启 Docker Desktop 的“登录时启动”，电脑重启并启动 Docker Desktop 时，所有长期服务会通过 `restart: unless-stopped` 自动恢复，无需再分别运行 `pnpm`。如果曾在 Docker Desktop 中手工停止容器，需要重新执行 `docker compose up -d`。`qwen3.7-plus` 和 `qwen3-vl-plus` 仍由容器通过百炼云端 API 调用，不是在 Docker 内运行的本地模型。

## 常用访问地址

| 服务 | 地址 | 说明 |
|---|---|---|
| 法律检索前端 | http://127.0.0.1:5173 | 法条检索、RAG 问答与公共知识库管理；局域网改用服务器 IP |
| 平台 RAG 网关 | http://127.0.0.1:3000/api/rag | 前端唯一允许访问的 RAG API 入口 |
| 项目 MinIO Console | http://localhost:9001 | 对象存储管理界面（业务 + Milvus 共用） |
| Milvus WebUI | http://127.0.0.1:9091/webui/ | 向量数据库 Web 控制台 |
| Milvus 健康检查 | http://127.0.0.1:9091/healthz | 服务健康状态 |
| PostgreSQL | localhost:5432 | 关系型数据库 |
| Milvus gRPC | localhost:19530 | 向量数据库客户端端口（知识库服务连接） |
| 知识库 RAG API | http://127.0.0.1:8000 | `/ready`、`/health`、`/documents/{id}/ingest`、`/search`、`/chat` |

## 环境信息

- 操作系统：Windows 11
- Python：3.11.9（DB 维护工具 + 知识库 RAG 服务）
- Node.js：22 LTS（一体化平台后端；`.nvmrc` 与 `package.json engines` 固定同一主版本）
- Docker：Docker Desktop + WSL2 部署

## 当前 RAG 验收状态

2026-07-16 已完成公共知识库上传第一版及 Chunk/耗时增强：前端支持公开法规、案例和工作资料上传，Node 平台完成 50MB/格式校验、SHA-256 去重、MinIO 原件、数据库事务登记、自动入库、状态/Markdown/Chunk 查询、失败重试、强制重建和分阶段耗时持久化。平台单元 30/30、HTTP E2E 15/15、前端组件 7/7、模拟浏览器 6/6、Python 99 passed + 5 subtests；真实文档 `doc_id=30` 强制重建后仍为 10 个 Chunk，ID 为 `30:m:0000` 至 `30:m:0009`，原问题继续命中文档 30。详见 [公共知识库上传第一版实施报告](docs/公共知识库上传第一版实施报告_2026-07-16.md)。

同日完成公共知识库多源文件追加：顶部上传区只新建独立知识库，入库成功的文档可通过“追加文件”把后续原件加入同一 `doc_id`；原 Chunk 保留，新旧来源共同参与检索与问答。“管理文件”可查看每个来源的 Markdown、Chunk、耗时并单独安全替换；“强制重建”会在所有来源处理成功后一次性替换整份向量数据。Alembic `d8e9f0a1b2c3` 新增 `oa.kb_document_source` 并回填历史主文件。当前基线为平台单元 40/40、HTTP E2E 15/15、前端组件 14/14、模拟浏览器 6/6、Python 102 passed + 5 subtests；真实文档 #38 在同一条目下保持 2 个来源、6 个 Chunk，主文件与追加/替换后的识别词均命中 #38，失败追加不影响旧数据，重建后活动 staging 文档、附件、来源、Milvus Chunk 和 MinIO 对象均为 0。

知识库管理页随后完成可选分页与独立预览：已登记文档默认每页 5 份，可选择 5、10、20、50、100、500 或 1000 份，切换后自动回到第一页；“查看 Markdown”和“查看 Chunk”使用新浏览器标签页打开可复制地址。Chunk 页继续保持每页 20 条，并把来源和页码写入 URL。当前前端组件 14/14、桌面/手机模拟浏览器 6/6、真实文档 #38 新标签页验收 2/2；新页面仍只请求 `/api/rag/*`，不会直连 8000、9000 或 19530。

2026-07-15 已新增 `law-platform-web` 和平台 RAG 网关：前端 Vitest 4/4、模拟浏览器测试 4/4（桌面 + 手机）、真实 RAG 浏览器测试 3/3；平台单元测试 22/22、HTTP E2E 15/15、Python pytest 93/93 + 5 subtests，前后端 lint 与 build 均通过。真实验收已确认劳动合同法第二十条、民法典第一千二百零二条和无依据拒答。浏览器端构建产物不含内部服务 Token，3000/8000/5432/9000/9001/9091/19530 均限制为本机监听。

2026-07-15 修复后完整回归已通过：Python 单测 80/80、在线阶段测试 53/53、文档级检索 15/15、法条级检索 11/11、Node 单测 17/17、HTTP E2E 12/12，ESLint 与 build 均通过。Milvus 当前为 23 个文档、198 个 Markdown chunk，持久层没有预签名 URL。

同日完成 RAG 权限与生产安全专项：当前 Python 自动化为 93 passed + 5 subtests；服务 Token + 数据库活动用户双层校验、部门/私有/案件权限、空授权范围短路、身份防伪、生产 fail-closed、非 root 容器和安全响应头均已验证。详情见 [RAG权限与生产安全处理报告](docs/RAG权限与生产安全处理报告_2026-07-15.md)。常驻实例暂为开发兼容模式，正式启用仍需 Node/API Gateway 登录态代理和生产密钥注入。

性能实测：顺序 mean=3.126s、P95=4.757s；5 路并发 5/5，wall=17.328s、mean=10.055s；10 路并发 10/10。详见 [RAG完整回归测试报告](docs/RAG完整回归测试报告_2026-07-15.md)。

历史 chapter 维护已完成：文档 3、5、6、8、18 已逐个安全重建，全库“节作为 chapter”归零，检索仍为文档级 15/15、法条级 11/11。详见 [RAG历史数据清理报告](docs/RAG历史数据清理报告_2026-07-15.md)。

## 迁移到 Apple Silicon Mac 的注意事项

后续计划迁移到 M 系列 Mac mini，大部分组件可直接迁移，但需提前验证以下几点：

### 1. Milvus 是最大风险点

Milvus 官方镜像长期以 `x86_64` 为主，M 系列 Mac 上可能：

- 通过 Rosetta 模拟运行，启动慢、CPU 占用高
- `etcd` 不稳定，容器偶尔掉线或重启
- 向量写入/检索性能明显下降

**建议先验证**：在 Mac mini 上直接运行根级 `docker-compose.yml`，然后执行：

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
curl http://127.0.0.1:9091/healthz
```

若 `milvus-standalone` 容器状态为 `healthy` 且返回 `OK`，则可以继续使用 Milvus。

### 2. 备选向量库方案

如果 Milvus 在 M 系列上无法稳定运行，可考虑：

| 方案 | 优点 | 缺点 |
|---|---|---|
| 强制 x86 模拟 + Rosetta | 不改代码 | 性能差，etcd 可能不稳定 |
| Qdrant | ARM64 原生支持极好 | 原生不支持 sparse vector 混合检索 |
| Weaviate | 有 ARM64 镜像 | 部署较重，hybrid 需额外配置 |

由于当前方案依赖 **BGE-M3 的 dense + sparse + hybrid search**，Milvus 仍是最优选择，建议优先验证保留。

### 3. 模型推理使用 MPS 加速（知识库服务）

知识库服务用 FlagEmbedding 加载 BGE-M3，在 M 系列上可指定 `mps` 设备（`.env` 中 `MODEL_DEVICE=mps`）：

```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel(
    "BAAI/bge-m3",            # 或本地模型路径
    use_fp16=False,
    device="mps",             # 回退用 "cpu"
)
```

注意：

- 模型须用 modelscope 下载到本地（本机 HuggingFace 不可达），启动带 `HF_HUB_OFFLINE=1`。
- FlagEmbedding 版本须锁 `1.2.10` + `transformers==4.44.2`（1.4.0 不兼容，详见 [law-rag-kb/README.md](law-rag-kb/README.md#-关键环境约束务必遵守)）。
- `FlagEmbedding` 的 sparse vector 输出需在 MPS 上单独测试。

### 4. 内存配置建议

同时运行 PostgreSQL、MinIO（单实例）、Milvus、Embedding/Reranker 模型及后续本地 LLM，建议 Mac mini **至少 16GB 内存，推荐 32GB**。8GB 机型会频繁 swap，体验较差。

## 下一步建议

1. 按 [平台后端NodeJS开发计划](docs/平台后端NodeJS开发计划.md) 完善 `law-platform-api/` 一体化平台（NestJS + Prisma）。
2. 扩充真实法律文档与人工生成评估集，持续验证 Qwen3.7 Plus 的答案忠实度、引用准确率和无依据拒答。
3. 继续进行 CPU 高并发长稳测试，并评估 GPU/独立 Reranker 动态 batching、OCR、旧 `.doc` 与外部 API 成本。
4. 在当前无登录的局域网验收版基础上补齐平台登录态，由网关注入内部服务 Token 和已认证用户 ID，再切换 `APP_ENV=production`。

## 相关文档

- [公共知识库上传第一版实施报告](docs/公共知识库上传第一版实施报告_2026-07-16.md)
- [简单 RAG 前端与局域网测试报告](docs/简单RAG前端与局域网测试报告_2026-07-15.md)
- [平台后端NodeJS开发计划](docs/平台后端NodeJS开发计划.md)
- [RAG开发计划](docs/RAG开发计划.md)
- [RAG整体链路测试报告](docs/RAG整体链路测试报告.md)
- [RAG完整回归测试报告（当前）](docs/RAG完整回归测试报告_2026-07-15.md)
- [RAG问题修复报告](docs/RAG问题修复报告_2026-07-15.md)
- [RAG历史数据清理报告](docs/RAG历史数据清理报告_2026-07-15.md)
- [RAG权限与生产安全处理报告](docs/RAG权限与生产安全处理报告_2026-07-15.md)
- [RAG全部功能测试报告（修复前基线）](docs/RAG全部功能测试报告_2026-07-15.md)
- [数据库设计](docs/数据库设计.md)
- [MinIO对象规则](docs/MinIO对象规则.md)
- [后端服务操作指南](law-rag-service/README.md)
- [Milvus 部署与操作指南](milvus-standalone/README.md)
