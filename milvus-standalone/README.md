# Milvus 向量数据库

Milvus 2.6.19 单机版（standalone），为法律 RAG 项目的知识库检索提供向量能力。

> 本目录原含独立 `docker-compose.yml`，现已**并入根级 `docker-compose.yml`** 统一编排（etcd + minio 已与业务基础设施合并）。本目录保留 `volumes/`（Milvus 数据卷）与本说明。

## 消费方

Milvus 由**知识库 Python 服务 `law-rag-kb`** 使用（pymilvus 连 `localhost:19530`）。当前 `kb_chunks` 统一保存 `{doc_id}:m:{idx}` Markdown chunk，图片使用稳定 `#img:{id}`，不持久化预签名 URL；一体化平台（Node）不直连 Milvus。详见 [RAG开发计划](../docs/RAG开发计划.md)。

## 组件

| 容器名 | 镜像 | 用途 |
|---|---|---|
| `milvus-etcd` | `quay.io/coreos/etcd:v3.5.25` | Milvus 元数据存储 |
| `milvus-standalone` | `milvusdb/milvus:v2.6.19` | Milvus 主服务 |

> MinIO 不再单列：Milvus 与业务共用同一个 MinIO 实例（`law-rag-minio`），使用其默认 bucket `a-bucket`。详见 [MinIO对象规则](../docs/MinIO对象规则.md)。

## 端口说明

| 端口 | 用途 |
|---|---|
| `19530` | Milvus gRPC，知识库服务通过 pymilvus 连接 |
| `9091` | Milvus HTTP，WebUI 与健康检查 |

## 启动 / 停止

Milvus 随根级 compose 一起启停：

```powershell
cd D:\law-rag-project
docker compose up -d          # 启动全部（含 milvus）
docker compose stop           # 停止
```

首次启动需拉取镜像，Milvus 健康检查有 90 秒启动宽限期。

## 完全删除 Milvus 容器与数据（谨慎）

```powershell
cd D:\law-rag-project
docker compose down -v
```

> 会删除持久化数据（含本目录 `milvus-standalone/volumes/` 下的 etcd/milvus 数据）。

## 查看日志

```powershell
docker logs -f milvus-standalone
docker logs -f milvus-etcd
```

## 健康检查

```powershell
curl http://127.0.0.1:9091/healthz
```

返回 `OK` 表示服务健康。

## WebUI

浏览器打开 `http://127.0.0.1:9091/webui/`。

## Python 连接示例（知识库服务）

```python
from pymilvus import connections, utility

connections.connect(alias='default', host='localhost', port='19530')
print(utility.get_server_version())
```

## 持久化数据位置

```text
milvus-standalone/volumes/
├── etcd/        # etcd 元数据
└── milvus/      # Milvus 运行时数据
```

> `volumes/minio/` 为合并前 Milvus 独立 MinIO 的遗留数据卷，现已弃用（Milvus 改用业务 MinIO 的 `a-bucket`），可酌情清理。

## 常见问题

1. **启动后 Milvus 一直 restarting**
   - 首次启动需等待 etcd 与 minio 就绪，Milvus 依赖它们。
   - 查日志：`docker logs -f milvus-standalone`
   - 确认端口 `19530`、`9091` 未被占用。

2. **端口冲突**
   - 若本机已有服务占用，可修改根级 `docker-compose.yml` 的端口映射。

3. **连接不上 Milvus**
   - 确认容器 healthy：`docker ps`
   - 确认 pymilvus 版本与服务端兼容（服务端 `v2.6.19`）。
