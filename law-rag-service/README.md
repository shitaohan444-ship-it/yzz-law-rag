# law-rag-service 数据库维护工具

法律 RAG 项目的 **Python 数据库维护工具集**，负责 PostgreSQL schema 迁移、字典种子、DB 校验与 Excel 设计源同步。

> ⚠️ 本目录**只做 DB 维护**，不含应用层：
> - 一体化平台业务后端 → NodeJS `law-platform-api/`（NestJS + Prisma），见 [平台后端NodeJS开发计划](../docs/平台后端NodeJS开发计划.md)
> - 知识库 RAG 后端 → Python `law-rag-kb/`（FastAPI + pymilvus + FlagEmbedding + Qwen3.7 Plus/Qwen3-VL，PDF/DOCX/TXT/MD/图片统一 Markdown 管线），见 [RAG开发计划](../docs/RAG开发计划.md)

## 当前状态

- 数据库 schema 已落地并校验通过：**80 张源表 / 9 个统计视图 / 200 外键 / 467 索引 / 145 字典类别 / 653 字典项 / 1653 总字段**
- Alembic 迁移链 head = `d5e7a3b9c1f2`（含 v2.16 设计修复 + v2.17 业务字段闭环 + MinIO 附件字段）
- `app/models/`（SQLAlchemy 模型）作为 Node 侧 Prisma schema 的参照源
- `app/services/attachment_service.py` 已闭环（MinIO + sys_attachment），Node 侧将对照重写
- 字典种子由 `seed_dict_data.py` 从 Excel 灌入

## OA 数据库初始化

```powershell
cd D:\law-rag-project\law-rag-service
.\.venv\Scripts\python.exe scripts\init_db.py
```

执行：Alembic 迁移 → 字典种子 → 校验。校验输出：

```text
[PASS] tables: 80
[PASS] views: 9
[PASS] foreign keys: 200
[PASS] indexes: 467
[PASS] dict types: 145
[PASS] dict items: 653
```

## 依赖服务

基础设施（PostgreSQL + MinIO + Milvus）已统一归**根级 `docker-compose.yml`** 编排，本目录不再单独起容器。启动见根 [README.md](../README.md)。

涉及本目录的服务：

| 容器名 | 镜像 | 用途 | 端口 |
|---|---|---|---|
| `law-rag-postgres` | `postgres:16` | 关系型数据库 | `5432` |
| `law-rag-minio` | `minio/minio:RELEASE.2024-12-18T13-15-44Z` | 对象存储（业务 + Milvus 共用） | API `9000` / Console `9001` |

## 环境变量

配置位于 [`.env`](.env)（本目录 DB/MinIO 配置，供 Python 工具使用）。基础设施凭据以根级 `.env` 为准。

```ini
POSTGRES_DB=law_rag
POSTGRES_USER=law_rag_user
POSTGRES_PASSWORD=law_rag_password
POSTGRES_PORT=5432
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001
PROJECT_NAME=law-rag-service
ENV=local
```

修改基础设施配置后，在项目根目录重启：`docker compose up -d --force-recreate`

## 启动 / 停止基础设施

```powershell
cd D:\law-rag-project
docker compose up -d      # 启动全部（postgres + minio + milvus）
docker compose stop       # 停止
```

## 常用脚本

| 脚本 | 用途 |
|---|---|
| `scripts/init_db.py` | 迁移 + 字典种子 + 校验（统一入口） |
| `scripts/seed_dict_data.py` | 从 Excel 07/08 表灌字典 |
| `scripts/generate_models_from_excel.py` | 从 Excel 06 表生成 SQLAlchemy 模型 |
| `scripts/sync_excel_business_field_closure.py` | v2.17 业务字段 Excel 同步 |
| `scripts/sync_excel_attachment.py` | MinIO 附件字段 Excel 同步 |
| `scripts/verify_attachment_service.py` | attachment_service 端到端验证 |
| `tmp_*_flow_test.py` | 各部门流程测试（DB 层回归基线） |

## 访问地址

| 服务 | 地址 | 账号 | 密码 |
|---|---|---|---|
| 项目 MinIO Console | http://localhost:9001 | `minioadmin` | `minioadmin123` |
| PostgreSQL | `localhost:5432` | `law_rag_user` | `law_rag_password` |

## 持久化数据

```text
law-rag-service/data/
├── postgres/    # PostgreSQL 数据（根级 compose 挂载）
└── minio/       # MinIO 对象数据（业务 + Milvus 共用实例，根级 compose 挂载）
```

## 与 Milvus 的关系

向量数据库 Milvus 与本目录服务同属根级 `docker-compose.yml` 编排。Milvus 通过 docker 网络 service 名 `minio:9000` 连接上述同一个 MinIO 实例（使用其默认 bucket `a-bucket`）。Milvus 的消费方是**知识库 Python 服务 `law-rag-kb`（pymilvus 连 `localhost:19530`）**，本目录不涉及。

## MinIO 单实例说明

项目只有一套 MinIO（`law-rag-minio`），业务附件与 Milvus 内部存储共用同一实例、各用各的 bucket：

| bucket | 用途 | 操作方 |
|---|---|---|
| `law-firm-files` | 法律文档附件 | 平台（Node）与知识库服务（Python）读写 |
| `a-bucket` | Milvus 默认 bucket（启动自建） | Milvus 内部，不要手动操作 |

业务上传/下载文件用 `localhost:9000`。

## schema 变更流程（四同步）

新增/修改字段时，必须四同步（缺一不可，否则 init_db 校验失败或 Excel 与 DB 脱节）：

1. 改 Excel 06(字段) / 07(字典类别) / 08(字典值) / 09(外键) / 10(索引)
2. 改 `app/models/` SQLAlchemy 模型
3. 写 Alembic 迁移（新 head）
4. 改 `scripts/init_db.py` 阈值（表/外键精确相等，索引/字典为下限）

完成后通知 Node 侧跑 `prisma db pull` 同步 `law-platform-api/prisma/schema.prisma`。

当前知识库迁移链已包含 `kb_document.description_summary` 与 `kb_document.body_markdown`（head `a1b2c3d4e5f6`），并补齐 `kb_document_image` 逐图审计模型。统一 Markdown 管线只在数据库保存稳定 `#img:{id}`，预签名 URL 由 `law-rag-kb` 读取接口现场生成。
