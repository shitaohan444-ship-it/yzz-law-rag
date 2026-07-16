# MinIO 对象规则

## 1. 概述

- 业务文件统一存储在 MinIO bucket `law-firm-files` 中。
- 数据库最终冻结后，业务表只保存 `bucket` + `object_key`，不保存文件实体。
- 本文档描述 `object_key` 的生成规则、目录结构与接口约定。
- **当前状态**：MinIO 基础服务、通用附件绑定和公共知识库上传均已完成。

## 2. 基础信息

| 项 | 值 |
|---|---|
| 服务 | `law-rag-minio`（业务 + Milvus 共用的唯一 MinIO 实例） |
| API 地址 | `http://localhost:9000` |
| Console 地址 | `http://localhost:9001` |
| Bucket | `law-firm-files`（项目唯一业务 bucket） |
| 持久化目录 | `law-rag-service/data/minio` |

> 说明：
> - 项目只有**一套 MinIO**：业务附件与 Milvus 向量库内部存储共用同一实例，各用各的 bucket，互不干扰。
> - 业务文件统一使用 `law-firm-files` bucket；Milvus 使用其默认 bucket（`a-bucket`，启动时自建）。旧的 `law-rag-files` bucket 已清理。
> - 不要手动操作 Milvus 的 `a-bucket`。

## 3. object_key 规则

### 3.1 通用格式

```text
{prefix}/{year}/{month}/{entity_no}/{category}/{yyyyMMddHHmmss}_{uuid8}_{filename}
```

说明：
- `yyyyMMddHHmmss` 与 `uuid8` 由 `minio_service.build_object_key()` 自动生成，保证唯一性并保留时间顺序。
- `category` 是**业务分类**，不是 PDF/Word 文件格式。

### 3.2 案件文件

```text
cases/{year}/{month}/{case_no}/{category}/{yyyyMMddHHmmss}_{uuid8}_{filename}
```

示例：

```text
cases/2026/07/CASE-2026-07001/evidence/20260710143015_a1b2c3d4_原告证据清单.pdf
cases/2026/07/CASE-2026-07001/contract/20260710143122_e5f6g7h8_委托代理合同.docx
```

### 3.3 线索文件

```text
leads/{year}/{month}/{lead_no}/{category}/{yyyyMMddHHmmss}_{uuid8}_{filename}
```

示例：

```text
leads/2026/07/LEAD-2026-07001/consultation/20260710143210_i9j0k1l2_咨询记录.pdf
```

### 3.4 合同协议文件

```text
contracts/{year}/{month}/{agreement_no}/{category}/{yyyyMMddHHmmss}_{uuid8}_{filename}
```

示例：

```text
contracts/2026/07/AGREE-2026-0001/agreement/20260710143305_m3n4o5p6_法律顾问合同.pdf
```

### 3.5 临时文件

```text
temp/{yyyyMMdd}/{uuid8}_{filename}
```

示例：

```text
temp/20260710/623a7a29_draft.txt
```

### 3.6 公共知识库原件

```text
knowledge-base/{year}/{month}/{sha256前2位}/{sha256}_{uuid8}_{filename}
```

该路径由 `law-platform-api/src/modules/knowledge-documents/` 使用。上传前计算 SHA-256；活动公共知识库附件受部分唯一索引保护，相同内容会复用已有文档，不重复上传和向量化。历史 `file_hash` 为空的附件不做自动批量回填。

## 4. 业务分类（category）

| category | 含义 |
|---|---|
| `evidence` | 证据材料 |
| `contract` | 合同文件 |
| `pleading` | 诉状、答辩状、上诉状等法律文书 |
| `court` | 开庭通知、传票、庭审笔录等法院材料 |
| `progress` | 办案进展材料 |
| `consultation` | 咨询记录 |
| `invoice` | 发票、收据 |
| `agreement` | 协议（如法律顾问协议、保密协议） |
| `other` | 其他未分类 |

> `category` 不是文件格式（如 `pdf`、`word`）。上层业务代码应根据文件的业务含义选择分类。

## 5. 字段说明

| 占位符 | 含义 | 来源 |
|---|---|---|
| `{year}` | 年份，4 位数字 | 业务时间 |
| `{month}` | 月份，2 位数字 | 业务时间 |
| `{case_no}` | 案件编号 | `oa_case.case_no`（待数据库最终确认） |
| `{lead_no}` | 案源编号 | `oa_marketing.lead_no`（待数据库最终确认） |
| `{agreement_no}` | 协议编号 | `oa_finance_contract.agreement_no`（待数据库最终确认） |
| `{category}` | 业务分类 | 见第 4 节 |
| `{filename}` | 原始文件名 | 用户上传文件名 |
| `{yyyyMMddHHmmss}` | 上传时间戳 | 自动生成 |
| `{uuid8}` | 8 位 UUID 前缀 | 自动生成 |

## 6. 服务实现

通用 MinIO 服务位于 `law-rag-service/app/services/minio_service.py`，提供：

| 方法 | 说明 |
|---|---|
| `ensure_bucket()` | 确保 bucket 存在 |
| `upload_file(object_key, data, content_type, overwrite=False)` | 上传 bytes / 文件路径 / 流；默认禁止覆盖 |
| `download_file(object_key)` | 下载并返回 `bytes` |
| `get_presigned_url(object_key, expires=3600, method="GET")` | 生成预签名 URL |
| `delete_file(object_key)` | 删除对象 |
| `file_exists(object_key)` | 检查对象是否存在 |
| `build_object_key(prefix, **kwargs)` | 按规则生成 object_key，自动拼接时间戳与 uuid8 |

## 7. 状态

- ✅ MinIO 基础设施已部署（`law-rag-minio`）
- ✅ Bucket `law-firm-files` 已创建，旧 bucket `law-rag-files` 已清理
- ✅ 基础 service 与 object_key 规则已实现
- ✅ 默认禁止覆盖同名文件
- ✅ 业务绑定已完成（v2.17）：`sys_attachment` 新增 `bucket`/`object_key`/`etag` 字段（迁移 `d5e7a3b9c1f2`，索引 467）；`app/services/attachment_service.py` 提供上传/下载/预签名/删除/多态关联；端到端验证通过（`scripts/verify_attachment_service.py`）
- ✅ 公共知识库上传第一版已完成：`knowledge-base/` 原件、SHA-256 去重、MinIO/数据库事务补偿和自动入库；唯一索引迁移为 `b6c7d8e9f0a1`

## 8. 已确认字段清单（v2.17 落地）

| 项 | 结论 |
|---|---|
| 通用文件对象表名 | `sys_attachment`（已落地，未改名） |
| MinIO 字段 | 已新增 `bucket`、`object_key`、`etag`（迁移 `d5e7a3b9c1f2`）；`file_size`/`mime_type`/`original_file_name`/`current_file_name` 原表已有 |
| `case_material` 关联字段 | `attachment_id`（外键已存在；业务模块拿到 `attachment_service.upload()` 返回的 id 后按需回填） |
| `kb_document` 关联字段 | `attachment_id`（已存在） |
| RAG 派生图片 | `rag-derived/{doc_id}/{source_hash}/{image_sha256}.{ext}`，由 `kb_document_image` 审计，不写 `sys_attachment` |
| Markdown 图片引用 | PostgreSQL/Milvus/聊天日志保存 `#img:{image_id}`；仅 `/documents/{id}/markdown`、`/search`、`/chat` 响应时按 `bucket_name/object_key` 生成预签名 URL |
| 业务编号字段名 | `case_main.case_no`、`crm_lead.lead_no`、`fin_fee_agreement.agreement_no` 均已确认存在，未改名 |
| 附件关系表 | `sys_attachment_relation` 用 `entity_type`（自由文本：party/lead/client/case/contract/invoice/document）+ `entity_id` 多态关联，`file_usage` 绑 `attachment_usage` 字典；无独立 `business_type` 字段 |

> **取值口径与技术债**：`sys_attachment.storage_type` 实际写入语义码 `'minio'`（与既有 `'nas'` 数据对称），`biz_type` 用语义码（如 `case`/`lead`/`fee_agreement`）。但字典 `biz_type`/`storage_type` 的 `item_value` 仍为数字（1-10 / 1-3），与实际数据字符串码不一致——这是与 `assigned_role` 同款的「字典数字 vs 实际字符串码」已知技术债，后续可统一。
