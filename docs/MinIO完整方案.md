# MinIO 完整方案

> 律所一体化系统的对象存储方案。本文档基于**双后端 + 单实例 MinIO** 的新框架编写——MinIO 服务端、数据库绑定、Node 侧附件服务均已验证；Python RAG 已完成统一 Markdown 入库、`rag-derived/` 派生图、切片后 `qwen3-vl-plus` 图片理解、`/search`、`/chat` 和法条/图片引用端到端验证。

---

## 1. 概述

- 业务文件统一存储在 MinIO bucket `law-firm-files`，数据库只保存 `bucket` + `object_key`，不保存文件实体。
- **单实例 MinIO**：业务附件（`law-firm-files`）与 Milvus 内部存储（默认 `a-bucket`）共用同一 MinIO 实例的不同 bucket，互不干扰。
- **两个应用消费方**：
  - `law-platform-api`（Node）：附件上传/下载/预签名/删除/多态关联（已实现）
  - `law-rag-kb`（Python）：只读业务原件，并在 `rag-derived/` 幂等写入图片审计派生对象（✅ 多模态入库链已实现）
- **DDL 边界**：数据库结构归 Python Alembic；Node 侧只读映射（`prisma db pull`），禁止 `prisma migrate`/`db push`。

## 2. 现状（已就绪）

| 组件 | 状态 | 位置 |
|---|---|---|
| MinIO 容器（单实例） | ✅ 运行中（healthy） | `law-rag-minio`，API 9000 / Console 9001 |
| PostgreSQL 容器 | ✅ 运行中（healthy） | `law-rag-postgres`，库 `law_rag`，schema `oa` |
| Milvus 容器 | ✅ 运行中（healthy） | `milvus-standalone`（19530）/ `milvus-etcd` |
| 业务 bucket | ✅ 已建 | `law-firm-files` |
| Milvus bucket | ✅ 启动自建 | `a-bucket`（与业务 bucket 共用同一 MinIO 实例） |
| 数据库绑定 | ✅ 已落地 | `sys_attachment` 含 `bucket`/`object_key`/`etag`（迁移 `d5e7a3b9c1f2`） |
| Node 附件服务 | ✅ 已实现并 e2e 验证 | [law-platform-api/src/modules/attachments/](../law-platform-api/src/modules/attachments/) |
| Python 附件服务 | ✅ 已实现（DB 维护侧参照） | [law-rag-service/app/services/attachment_service.py](../law-rag-service/app/services/attachment_service.py) |
| Python RAG 服务 | ✅ 阶段 0–8 文本与多模态链路可用 | [law-rag-kb/](../law-rag-kb/)（读业务原件、写 `rag-derived/`、写 Milvus、提供 `/search` `/chat`） |
| Node 附件 HTTP API | ✅ 已实现（见 §7.2） | `law-platform-api` AttachmentsController |

> 旧 bucket `law-rag-files` 已清理；旧 `milvus-minio` 独立实例已合并删除。MinIO 为**单一实例**：业务（`law-firm-files`）与 Milvus（默认 `a-bucket`，启动自建）共用同一实例的不同 bucket。**不要手动操作 Milvus 的 `a-bucket`**。

## 3. 架构与部署

### 3.1 容器（根级 [docker-compose.yml](../docker-compose.yml)）

MinIO 与 PostgreSQL、Milvus 一起由根级 `docker-compose.yml` 统一编排（子目录原 `docker-compose.yml` 已并入根级并删除）。MinIO 为**单一实例**，业务附件与 Milvus 内部存储共用：

| 容器 | 镜像 | 端口 | 持久化 |
|---|---|---|---|
| `law-rag-minio` | `minio/minio:RELEASE.2024-12-18T13-15-44Z` | 9000(API) / 9001(Console) | `./law-rag-service/data/minio:/data` |
| `law-rag-postgres` | `postgres:16` | 5432 | `./law-rag-service/data/postgres` |
| `milvus-etcd` | `quay.io/coreos/etcd:v3.5.25` | — | `./milvus-standalone/volumes/etcd` |
| `milvus-standalone` | `milvusdb/milvus:v2.6.19` | 19530 / 9091 | `./milvus-standalone/volumes/milvus` |

- 全部容器同属 `law-rag-net` bridge 网络。
- **Milvus 连业务 MinIO**：通过 service 名 `minio:9000`（容器网络内）；凭据 `MINIO_ACCESS_KEY_ID`/`MINIO_SECRET_ACCESS_KEY` 注入自根级 `.env` 的 `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`——业务 MinIO 密码 `minioadmin123` ≠ Milvus 默认 `minioadmin`，**必须显式注入**否则 healthcheck 一直失败。Milvus 自建并使用默认 bucket `a-bucket`，与业务 `law-firm-files` 隔离。
- 启停：`cd D:\law-rag-project && docker compose up -d` / `docker compose down`（仅停；数据在 volume）。

### 3.2 连接配置

业务 MinIO 凭据统一来自根级 [.env](../.env)（`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`），各消费方按自己的变量名读取（值相同）：

**[law-platform-api/.env](../law-platform-api/.env)**（Node 附件服务）：
```dotenv
DATABASE_URL=postgresql://law_rag_user:law_rag_password@localhost:5432/law_rag
MINIO_ENDPOINT=localhost
MINIO_PORT=9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=law-firm-files
MINIO_USE_SSL=false
```

**[law-rag-kb/.env](../law-rag-kb/.env.example)**（Python RAG，复制 .env.example 为 .env）：
```dotenv
MINIO_ENDPOINT=localhost
MINIO_PORT=9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=law-firm-files
MINIO_USE_SSL=false
```

> 两个应用消费方变量名相同（`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`），值一致；Milvus 用另一组变量名 `MINIO_ACCESS_KEY_ID`/`MINIO_SECRET_ACCESS_KEY`（见 §3.1 / §11）。`DATABASE_URL` 必须用 `postgresql://`（非 Python 的 `postgresql+psycopg://`），schema `oa` 由 Prisma `schemas=["oa"]` 声明。

### 3.3 Console 手动访问

- 地址：`http://localhost:9001`，账号 `minioadmin` / `minioadmin123`。
- 可见两个 bucket：`law-firm-files`（业务）+ `a-bucket`（Milvus，勿动）。
- 用于浏览/手动上传/删除业务对象。**生产环境务必改密钥 + 最小权限 service account**（见 §9.3）。

## 4. object_key 规则

### 4.1 通用格式

```
{prefix}/{year}/{month}/{entity_no}/{category}/{yyyyMMddHHmmss}_{uuid8}_{filename}
```

- `yyyyMMddHHmmss` 与 `uuid8` 由 `MinioService.buildObjectKey()` 自动生成（**UTC 时间**），保证唯一且保留时间顺序。
- `category` 是**业务分类**，不是 PDF/Word 文件格式。

### 4.2 前缀与业务编号

| prefix | 业务 | entity_no 来源 |
|---|---|---|
| `cases` | 案件文件 | `oa.case_main.case_no` |
| `leads` | 线索文件 | `oa.crm_lead.lead_no` |
| `contracts` | 合同协议 | `oa.fin_fee_agreement.agreement_no` |
| `temp` | 临时文件 | （无，走 `temp/{yyyyMMdd}/{uuid8}_{filename}`） |

### 4.3 业务分类 category

| category | 含义 |
|---|---|
| `evidence` | 证据材料 |
| `contract` | 合同文件 |
| `pleading` | 诉状/答辩状/上诉状等法律文书 |
| `court` | 开庭通知/传票/庭审笔录等法院材料 |
| `progress` | 办案进展材料 |
| `consultation` | 咨询记录 |
| `invoice` | 发票/收据 |
| `agreement` | 协议（法律顾问协议、保密协议等） |
| `other` | 其他未分类 |

示例：`cases/2026/07/CASE-2026-07001/evidence/20260710143015_a1b2c3d4_原告证据清单.pdf`

## 5. 数据库绑定

### 5.1 `sys_attachment`（文件主表，schema oa，31 列）

关键字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | BigInt PK | 附件 ID |
| `biz_type` | String | 业务对象类型语义码（`case`/`lead`/`fee_agreement`…） |
| `biz_id` | BigInt | 业务对象 ID（多态，无 FK） |
| `file_name` / `file_ext` / `mime_type` / `file_size` | — | 文件元信息 |
| `storage_type` | String | 固定 `'minio'`（与 `'nas'` 对称） |
| `storage_path` | String | 兼容 NAS 历史字段，存 object_key |
| `bucket` | String? | MinIO bucket（v2.17 新增） |
| `object_key` | String? | 对象键，下载/预签名/RAG 读取的定位依据（v2.17 新增） |
| `etag` | String? | 对象 etag，完整性校验（v2.17 新增） |
| `ai_index_status` | String | 是否已进入 AI 知识库索引流程（`pending`/`indexed`/…）—— RAG 入库的驱动字段 |
| `uploaded_by` / `uploaded_at` | — | 上传人/时间 |
| `status` | String | `active`/`disabled` |
| `deleted_at` | DateTime? | 软删除时间，空=有效 |
| `created_at`/`updated_at`/`created_by`/`updated_by` | — | 审计字段（**无 server default，代码层填**） |

> 历史 NAS 字段（`file_hash`/`ocr_text`/`relative_path`/`folder_path`/`storage_repository_id`/`last_checked_at`）在 DDL 里均 nullable，MinIO 场景不填。

### 5.2 `sys_attachment_relation`（多态关联表）

把附件绑到任意业务实体（party/lead/client/case/contract/invoice/document）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `attachment_id` | BigInt | 指向 sys_attachment |
| `entity_type` | String | 业务对象类型（自由文本） |
| `entity_id` | BigInt | 业务对象 ID（多态，无 FK） |
| `file_usage` | SmallInt? | 用途（绑 `attachment_usage` 字典） |
| `is_primary` | SmallInt | 是否主附件 |

## 6. MinIO 消费方与附件服务能力

### 6.1 消费方总览

| 消费方 | 语言 | bucket | 操作 | 状态 |
|---|---|---|---|---|
| `law-platform-api` 附件服务 | Node | `law-firm-files` | 读写删（上传/下载/预签名/删除/绑定） | ✅ 已实现 |
| `law-rag-kb` RAG 服务 | Python | `law-firm-files` | 读原件；幂等写 `rag-derived/` 图片审计对象 | ✅ 多模态入库链已实现 |
| `law-rag-service` DB 工具 | Python | `law-firm-files` | 读写（维护/校验，参照基线） | ✅ 已实现 |
| Milvus | — | `a-bucket` | 内部读写（向量/索引段） | ✅ 运行中（勿手动操作） |

### 6.2 Node 附件服务（[law-platform-api](../law-platform-api/src/modules/attachments/)）

**`MinioService`**（[minio.service.ts](../law-platform-api/src/core/minio/minio.service.ts)）—— 通用对象存储层：

| 方法 | 说明 |
|---|---|
| `ensureBucket(bucket?)` | 确保 bucket 存在 |
| `static buildObjectKey(prefix, opts)` | 按 §4 规则生成 object_key |
| `uploadFile(objectKey, data, opts)` | 上传 Buffer，默认禁止覆盖；返回 `{bucket, objectKey, etag, size}` |
| `downloadFile(objectKey, bucket?)` | 下载返回 Buffer |
| `getPresignedUrl(objectKey, opts)` | 预签名 URL（GET/PUT，默认 1h） |
| `deleteFile(objectKey, bucket?)` | 删除对象（S3 幂等） |
| `fileExists(objectKey, bucket?)` | 检查存在（404 三路宽容判断） |
| `static guessContentType(filename)` | 按后缀推断 MIME |

**`AttachmentService`**（[attachment.service.ts](../law-platform-api/src/modules/attachments/attachment.service.ts)）—— 业务绑定层：

| 方法 | 说明 | 事务 |
|---|---|---|
| `upload(input)` | 上传 MinIO + 写 sys_attachment（+可选 relation），返回 attachment_id | 自持事务 + **写库失败补偿删除对象** |
| `download(attachmentId)` | 下载附件 → Buffer | — |
| `getPresignedUrl(attachmentId, expires)` | 预签名 URL | — |
| `delete(attachmentId, soft=true)` | **先提交 DB 软删 → 后删 MinIO** | 自持事务 |
| `bindToEntity(tx, input)` | 写 sys_attachment_relation | 接收外部 tx，可组合进调用方事务 |

### 6.3 Python RAG 读取与派生图写入（law-rag-kb，✅ 已实现）

`law-rag-kb` 只读业务原件，业务附件上传仍归 Node；多模态链路会幂等写入非业务派生图片：

```
sys_attachment / kb_document 取 object_key
        ↓
minio SDK 下载文档原件（law-firm-files bucket）
        ↓
结构化解析 → 图片写 rag-derived/{doc_id}/{source_hash}/ 并建立 pending 审计记录
        ↓
PDF/DOCX/TXT/MD/图片转初始 Markdown → draft 结构化切片
        ↓
含图 chunk 调 qwen3-vl-plus → 分类写 metadata → 描述/OCR回填 Markdown
        ↓
文档概述 + 超长块二次整形 → BGE-M3 向量化
        ↓
存 Milvus Markdown chunk（a-bucket，经 pymilvus 19530）
        ↓
回写 sys_attachment.ai_index_status = 'success'
```

技术栈：`minio` Python SDK + PyMuPDF/python-docx/Pillow + `pymilvus` + FlagEmbedding（BGE-M3 / bge-reranker-v2-m3）+ 阿里云百炼 `qwen3.7-plus`/`qwen3-vl-plus`。派生图由 `kb_document_image` 记录，不创建业务附件行；PostgreSQL、Milvus 和聊天日志只保存稳定 `#img:{id}`，预签名 URL 仅在 API 读取时生成。详见 [RAG多模态VL实施说明](RAG多模态VL实施说明.md)。

### 6.4 事务与健壮性设计（Node 附件服务）

- **upload**：MinIO put 在事务外先做 → DB 写包进 `prisma.$transaction` → 写库失败则 best-effort `deleteFile` 清理已传对象 + rethrow（修复 Python 版对象泄漏缺陷）。
- **delete**：先提交 DB 软删 → 后删 MinIO（修复 Python 版「MinIO 删成功但 DB 提交失败 → 行还在对象已丢」的脏状态）。删 MinIO 失败仅记日志，孤儿对象由扫描任务补救。
- **审计字段**：DB 无 `server_default`，代码层每次写 `const now = new Date()` 显式赋值（不手加 `@default(now())`，会被 db pull 覆盖）。

## 7. 操作 MinIO 的方式

### 7.1 方式一：Node service 层调用（✅ 现在可用）

在任意 NestJS 业务模块里注入 `AttachmentService` 直接调用：

```ts
import { AttachmentService } from '../../core/.../attachment.service';

@Injectable()
export class CaseService {
  constructor(private readonly attachments: AttachmentService) {}

  async uploadEvidence(caseId: bigint, file: Buffer, filename: string, uploader: bigint) {
    return this.attachments.upload({
      fileData: file,
      filename,
      bizType: 'case',
      bizId: caseId,
      category: 'evidence',
      uploadedBy: uploader,
      entityType: 'case',      // 同步写 sys_attachment_relation
      entityId: caseId,
      fileUsage: 2,             // attachment_usage 字典值
    });
  }
}
```

适用：Node 后端业务模块内部存取文件（案件、线索、合同、发票等业务流程里调）。

### 7.2 方式二：HTTP API（✅ 已实现，阶段 3）

前端/外部客户端通过 HTTP 调用。[attachments.controller.ts](../law-platform-api/src/modules/attachments/attachments.controller.ts) 已实现 5 端点：

| 方法 | 路由 | 说明 |
|---|---|---|
| POST | `/attachments/upload` | multipart 上传，写 MinIO + sys_attachment |
| GET | `/attachments/:id/download` | 返回文件流（或 302 到 presigned url） |
| GET | `/attachments/:id/presigned-url` | 返回预签名 URL（前端直连 MinIO 下载） |
| DELETE | `/attachments/:id` | 软删 |
| POST | `/attachments/:id/bind` | 追加多态关联 |

**实施要点**：
- `uploaded_by` 从 JWT 鉴权 token 取，不由客户端传。
- **BigInt 序列化**：`id`/`file_size` 等是 bigint，`JSON.stringify` 会抛错——加全局 BigInt→string replacer，或 DTO 里 `.toString()`。
- 鉴权方案未定（阶段 3 启动前需先定 JWT/会话策略）。
- 大文件考虑前端直传 MinIO（PUT 预签名 URL），后端只落库——后续优化项。

### 7.3 方式三：RAG 入库读取（✅ law-rag-kb，入库链已实现）

`law-rag-kb` 通过 `POST /documents/{doc_id}/ingest`（:8000）触发文档入库，内部用 minio SDK 按 `object_key` 从 `law-firm-files` 拉取文档原件。典型流程（Python 伪代码）：

```python
from minio import Minio
from pymilvus import MilvusClient

client = Minio(MINIO_ENDPOINT, MINIO_PORT,
               access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY,
               secure=MINIO_USE_SSL)

# 1. 从 oa.sys_attachment 取 object_key（ai_index_status='pending'）
# 2. 下载文档原件
stream = client.get_object('law-firm-files', object_key)
content = stream.read(); stream.close(); stream.release_conn()
# 3. 解析 → 切片 → BGE-M3 向量化
# 4. 存 Milvus（pymilvus 连 :19530，Milvus 内部落 a-bucket）
# 5. 回写 sys_attachment.ai_index_status = 'indexed'
```

> law-rag-kb 不删改业务原件，只能额外写 `rag-derived/` 派生图片；写 Milvus 走 pymilvus，不直接操作 MinIO 的 a-bucket。

### 7.4 方式四：MinIO Console（手动）

`http://localhost:9001` 登录后手动上传/下载/删除。适用：临时排查、人工补传、运维清理。**不推荐日常业务用**（绕过数据库绑定，会产生孤立对象）。**切勿操作 `a-bucket`**。

## 8. 端到端验证

验证脚本：[test/attachment.e2e-spec.ts](../law-platform-api/test/attachment.e2e-spec.ts)，9 步断言连真实 PG + 真实 MinIO，固定文件名 `_attachment_service_probe.pdf` 保证幂等可重跑。

```bash
cd law-platform-api
pnpm verify     # 跑 Jest e2e
```

9 步：①cleanup 预清理 → ②取种子 case_main + sys_employee → ③upload → ④断言 sys_attachment 字段（bucket/storage_type/file_size/object_key 含 case_no/etag）→ ⑤MinIO 对象存在 → ⑥download 字节一致 → ⑦presigned url 含 bucket → ⑧relation 行 → ⑨软删后对象消失 + deleted_at 非空。

> 前置：需有种子数据（case_main + sys_employee），如无先跑 `law-rag-service` 的 `tmp_case_management_flow_test.py`。
> 单实例合并后已验证：4 容器 healthy，Milvus 正常读写业务 MinIO（`a-bucket`），业务数据连续（alembic 仍 head `d5e7a3b9c1f2`）。

## 9. 运维

### 9.1 备份

- MinIO 数据 volume：`law-rag-service/data/minio`（容器内 `/data`），含 `law-firm-files` + `a-bucket` 两个 bucket。
- 备份方式：停机冷备 volume，或用 `mc mirror` 按 bucket 分别同步到异地。
- **数据库与对象存储要一起备**——单备对象无 `sys_attachment` 元数据则无法检索。
- `a-bucket`（Milvus 向量）：可由文档原件重新入库重建，优先级低于业务 bucket；但重建成本高（需重跑 RAG 入库），生产建议同备。

### 9.2 生命周期与清理

- `temp/` 前缀对象：定期清理（如 7 天），`mc rm --recursive --older-than 7d minio/law-firm-files/temp/`。
- **孤儿对象扫描**：`deleted_at != null` 但 MinIO 仍存在的对象（delete 时 MinIO 删除失败的残留），定期扫描清理；反之 DB 已删但对象丢失的，置 `file_exists_flag='0'`。
- 软删保留：`sys_attachment` 软删后行保留（`deleted_at` 非空），对象删除；如需彻底清理，加定时任务物理删超期软删行。
- ⚠️ **清理脚本必须显式限定 bucket 为 `law-firm-files`**，绝不触碰 `a-bucket`（会损坏 Milvus）。

### 9.3 权限

- 当前用 root 凭据 `minioadmin`/`minioadmin123`（开发环境）。
- 生产：改强 root 密钥 + 为应用建最小权限 service account（仅 `law-firm-files` 的读写删；Milvus 用独立 account 仅 `a-bucket`）。
- **改 MinIO 密钥需四处同步**：根级 `.env`（`MINIO_ROOT_USER/PASSWORD`）+ `law-platform-api/.env` + `law-rag-kb/.env` + `docker-compose.yml` 里 milvus standalone 的 `MINIO_ACCESS_KEY_ID/SECRET_ACCESS_KEY` 注入。漏改任一处，对应消费方连接失败。
- 凭据走 `.env`，已在 `.gitignore`，不进版本库。

### 9.4 监控

- 容器 healthcheck：MinIO `mc ready local`、Milvus `curl :9091/healthz`（compose 已配）。
- 关键指标：bucket 用量、对象数、上传失败率（`AttachmentService` warn/error 日志）、Milvus `scope=MinioFileWriter` 读写异常。

## 10. 后续路线

| 项 | 内容 | 状态 |
|---|---|---|
| 平台阶段 1-2 | NestJS 骨架 + MinioService + AttachmentService + e2e | ✅ |
| 平台阶段 3 | AttachmentsController + DTO（§7.2，鉴权 TODO） | ✅ |
| 平台阶段 4 | 业务模块迁移（**案件材料 case_material ✅** / finance / marketing…）调附件服务 | 进行中 |
| 平台阶段 5 | 9 个统计视图（`$queryRaw`） | 待 |
| **知识库 law-rag-kb** | 文本/图片入库、VL过滤与描述、hybrid检索、reranker、法条/图片引用、Qwen3.7 Plus `/chat`、文档/案件授权和生产安全基线均已验证；平台登录网关联调、旧DOC、异步化与真实图片评估集待续 |

> RAG 已独立为 Python 服务 `law-rag-kb`（原"RAG 塞进 Node"方案废弃）。Node 平台不直连 Milvus。详见 [平台后端NodeJS开发计划.md](平台后端NodeJS开发计划.md) / [RAG开发计划.md](RAG开发计划.md)。

## 11. 注意事项（踩坑记录）

1. **Prisma 用 6.x，不是 7**：Prisma 7 破坏性变更（schema 不再支持 `url=`，强制 driver adapter）。锁 6.19.3。
2. **tsx 不支持 `emitDecoratorMetadata`**：带 Nest DI 的代码不能用 tsx 跑（DI 注入 undefined）。验证用 Jest + ts-jest；`Test.createTestingModule().compile()` 后必须 `.init()` 才触发 onModuleInit。
3. **minio JS SDK 错误处理**：`statObject` 不存在对象抛 S3Error，错误形态不一（code `NotFound`/`NoSuchKey`、statusCode 可能缺失、message `Not Found`）——`fileExists` 三路宽容判断。`putObject` 返回 etag 不稳定 → put 后 `statObject` 取权威值。`getObject` 返回 stream 需 `streamToBuffer`。
4. **db pull model 名是 snake_case**：`prisma.sys_attachment`（非驼峰），字段也 snake_case。
5. **审计字段无 server default**：代码层填，不手加 `@default(now())`。
6. **时区**：`uploaded_at` 与 object_key 的 year/month/timestamp 全用 UTC，否则跨时区机器上断言偶发失败。
7. **Win Git Bash**：`cd` 后 shell cwd 持久化，相对路径易双层；操作文件用绝对路径。`npx` 走 npm 缓存易 EPERM，用 `pnpm dlx`/`pnpm -C`。
8. **MinIO 凭据变量名三套**（单实例合并后易混）：
   - MinIO server / 根 `.env`：`MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`
   - Node + Python 应用 `.env`：`MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`（值同上）
   - Milvus（docker-compose env）：`MINIO_ACCESS_KEY_ID` / `MINIO_SECRET_ACCESS_KEY`（注入自 root 变量）
   - ⚠️ env 名是 `MINIO_ACCESS_KEY_ID`，**不是** `MINIO_ACCESS_KEY`——Milvus 不传或传错则 healthcheck 一直失败。
9. **单实例 bucket 隔离**：业务代码/console/清理脚本只操作 `law-firm-files`；`a-bucket` 是 Milvus 内部数据，**手动删/改会损坏 Milvus**。Console 里两个 bucket 并存，操作前确认 bucket 名。

---

**相关文件**：[MinIO对象规则.md](MinIO对象规则.md)（object_key 规则详版）｜[平台后端NodeJS开发计划.md](平台后端NodeJS开发计划.md)｜[RAG开发计划.md](RAG开发计划.md)｜[数据库设计.md](数据库设计.md)
