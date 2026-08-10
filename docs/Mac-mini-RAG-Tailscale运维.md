# Mac mini RAG Tailscale 运维（历史文档，当前不使用）

> **注意**：本文档为 2026-08-03 短暂使用 Tailscale 固定地址互联期间的运维口径。**当前系统已切回纯局域网通信**，Tailscale 不再作为 platform-api 与 Mac RAG 之间的正式通信路径，也不作为 Mac 连接 Win11 PostgreSQL/MinIO/Milvus 的路径。
>
> 请使用 [Mac mini RAG 局域网运维](Mac-mini-RAG局域网运维.md) 作为现行运维文档。本文档保留作为 Tailscale 迁移过程的历史参考。

本文档是 Win11 主机 + Mac mini 通过 Tailscale 固定地址互联双机部署的唯一运维口径。涉及普通用户操作时，请只用 OA 前端；本文所有后端接口均不对普通用户开放。

## 1. 当前系统用途

系统用于律师事务所知识库文档的上传、解析、向量化和智能检索。新文档的解析和向量化由 Mac mini 协处理，其余检索、问答和高级数据操作由 Win11 主机上的旧 RAG 提供。

## 2. 当前固定地址

| 角色 | Tailscale 地址 | 说明 |
|---|---|---|
| Win11 主机 | `100.115.212.72` | 前端、平台后端、旧 RAG、PostgreSQL、MinIO、Milvus |
| Mac mini | `100.68.157.108` | 新文档解析、切片、向量化协处理 |
| OA 固定地址 | `http://100.115.212.72:5173` | 同一 tailnet 内设备可用 |
| Mac RAG 服务 | `http://100.68.157.108:18000` | 后端接口，**非普通用户操作页面** |
| Win11 旧 RAG（内部） | `http://rag-api:8000` | Docker 内网地址，仅供平台后端调用 |

当前运行配置：

```text
RAG_DOCUMENT_API_BASE_URL=http://100.68.157.108:18000
RAG_DOCUMENT_ROUTE_MODE=initial_mac
RAG_DOCUMENT_MAC_ALLOWLIST=         # 为空
LawRagImportBridge=Disabled
```

Mac 服务运行态：

```text
LaunchAgent = com.yzz.law-rag-kb
监听地址   = 0.0.0.0:18000
processor  = mac-mini
APP_ENV    = production
AUTH_ENABLED             = true
DOCUMENT_MUTATIONS_ENABLED = true
MPS 可用
```

## 3. Tailscale 通信架构

Win11 和 Mac mini 必须登录同一 tailnet。两台设备通过 Tailscale 固定地址互联，不再依赖 `192.168.x.x` 局域网地址。

### Win11

```text
Tailscale 固定地址：100.115.212.72
已启用 Run Unattended
承载：前端 :5173、平台后端 :3000（127.0.0.1）、
      旧 RAG :8000（Docker 内网）、PostgreSQL :5432、
      MinIO :9000、Milvus :19530
```

### Mac mini

```text
Tailscale 固定地址：100.68.157.108
仅承载：文档处理服务 :18000（0.0.0.0 监听）
依赖：Win11 PostgreSQL（100.115.212.72:5432）
       Win11 MinIO（100.115.212.72:9000）
       Win11 Milvus（100.115.212.72:19530）
```

### 通信方向

```text
Win11 platform-api
  → http://100.68.157.108:18000（Mac RAG 文档 ingest）

Mac RAG
  → 100.115.212.72:5432（PostgreSQL）
  → 100.115.212.72:9000（MinIO）
  → 100.115.212.72:19530（Milvus）
```

### Tailscale 安全约束

- 不使用 Exit Node
- 不启用 Funnel
- 不公开 18000、5432、9000、19530 到公网
- 访问 OA 的其他设备也需加入同一 tailnet
- Tailscale 地址固定，不取消现有主机防火墙和 Docker 监听限制
- 未安装 Tailscale 的设备可通过 Wi-Fi 局域网 IP 继续访问 5173，但局域网 IP 易变化，**不得写入项目文档作为正式固定地址**

## 4. OA 访问方式

```text
http://100.115.212.72:5173
```

这是同一 tailnet 内设备的固定访问地址。未安装 Tailscale 的局域网设备可使用 Win11 当前局域网 IP（如 `192.168.0.187:5173`），但该地址可能随 Wi-Fi 切换而变化，仅作为临时方案。

浏览器只访问前端，由前端容器经 Docker 内网转发到平台后端，不直连任何数据库或 RAG 服务。

## 5. Mac RAG 服务地址

```text
http://100.68.157.108:18000
```

**仅由 Win11 platform-api 调用，不是普通用户操作页面**。提供 `/health`、`/ready` 和文档 ingest 接口。监听 `0.0.0.0:18000`，platform-api 通过 Tailscale 固定地址访问。

## 6. `initial_mac` 路由规则

### 由 Mac mini 处理

- 普通新文档首次 ingest
- `force=false`

### 暂时仍由 Win11 旧 RAG 处理

- `force=true`
- `promote`
- `promote-source`
- `rebuild-sources`
- `batch-delete`
- `verify-restore`
- staging 删除
- 其他高级文档 Mutation

### 始终由 Win11 旧 RAG 提供

- 文档状态读取
- Markdown 预览
- Chunk 预览
- 知识库搜索
- 聊天
- Drafting Lite

**重要**：Mac 失败时不得自动回退 Win11 旧 RAG 处理首次 ingest。Mac 不可用时该次 ingest 失败，不会悄悄改由旧 RAG 处理。

## 7. 新文档处理流程

```text
OA 上传新知识库文档
→ Win11 platform-api
→ 通过 Tailscale 调用 Mac mini（http://100.68.157.108:18000）
→ Mac mini 解析文档
→ Mac mini 按 Markdown 结构切片
→ Mac mini 用 BGE-M3 + MPS 生成 Dense/Sparse 向量
→ 通过 Tailscale 写入 Win11 Milvus（100.115.212.72:19530）
→ 更新 Win11 PostgreSQL 状态（100.115.212.72:5432）
→ Win11 旧 RAG 继续提供搜索、聊天和文档读取
```

Mac mini 不持有数据，只负责计算；原始文件、向量、状态最终都落在 Win11 的 MinIO、Milvus 和 PostgreSQL 中。

## 8. Win11 重启后的检查

```powershell
Set-Location D:\law-rag-project

tailscale status

tailscale ping 100.68.157.108

Test-NetConnection `
  -ComputerName 100.68.157.108 `
  -Port 18000

docker compose ps

docker compose exec -T platform-api `
  printenv RAG_DOCUMENT_API_BASE_URL

docker compose exec -T platform-api `
  printenv RAG_DOCUMENT_ROUTE_MODE

docker compose exec -T platform-api `
  printenv RAG_DOCUMENT_MAC_ALLOWLIST

Invoke-RestMethod `
  -Uri "http://100.68.157.108:18000/ready" `
  -TimeoutSec 180 |
Format-List
```

正确结果：

```text
Tailscale Connected
Tailscale ping 100.68.157.108 成功
TcpTestSucceeded=True
platform-api=healthy
旧RAG=healthy
PostgreSQL=healthy
MinIO=healthy
Milvus=healthy
RAG_DOCUMENT_API_BASE_URL=http://100.68.157.108:18000
RAG_DOCUMENT_ROUTE_MODE=initial_mac
RAG_DOCUMENT_MAC_ALLOWLIST为空
Mac status=ready
pg=ok
minio=ok
milvus=ok
embedding=ok
reranker=ok
authentication=ok
```

重启流程：

1. 确认 Tailscale Connected
2. 确认 Run Unattended 仍启用
3. 启动 Docker Desktop
4. 执行 `docker compose ps`
5. 检查 Mac `/ready`
6. 不需要修改 `.env`

## 9. Mac mini 重启后的检查

```bash
tailscale status

tailscale ping 100.115.212.72

for port in 5432 9000 19530; do
  nc -vz -G 5 100.115.212.72 "$port"
done

launchctl print gui/$(id -u)/com.yzz.law-rag-kb |
grep -E 'state =|pid =|last exit code'

lsof -nP -iTCP:18000 -sTCP:LISTEN

curl -fsS http://127.0.0.1:18000/ready |
python3 -m json.tool

curl -fsS http://100.68.157.108:18000/ready |
python3 -m json.tool
```

正确结果：

```text
Tailscale Connected
Tailscale ping 100.115.212.72 成功
Win11 5432/9000/19530 端口均可达
LaunchAgent state = running
仅一个 Uvicorn 进程
监听地址 = *:18000
status=ready
pg/minio/milvus=ok
embedding/reranker=ok
authentication=ok
```

重启流程：

1. 登录 yzz 用户
2. 确认 Tailscale Connected
3. 检查 LaunchAgent
4. 必要时执行：

```bash
launchctl kickstart -k gui/$(id -u)/com.yzz.law-rag-kb
```

5. 检查 `/ready`
6. 不需要修改 `.env`

## 10. 更换网络后的处理方式

更换 Wi-Fi、路由器或办公地点后，原则上**不再修改 `.env`**。只需确认 Tailscale 状态：

### Win11

```powershell
tailscale status
tailscale ping 100.68.157.108
Test-NetConnection 100.68.157.108 -Port 18000
```

### Mac

```bash
tailscale status
tailscale ping 100.115.212.72
curl -fsS http://100.68.157.108:18000/ready
```

如果两台机器 Tailscale 均为 Connected 且端口正常，不修改任何 IP 配置。建议在路由器中为两台机器固定 DHCP 地址，优先使用 Tailscale 固定地址。

## 11. Tailscale 连通性检查

### 基本检查（Win11）

```powershell
tailscale status
tailscale ping 100.68.157.108
```

### 基本检查（Mac）

```bash
tailscale status
tailscale ping 100.115.212.72
```

### 业务端口检查（Win11）

```powershell
Test-NetConnection -ComputerName 100.68.157.108 -Port 18000
```

### 业务端口检查（Mac）

```bash
for port in 5432 9000 19530; do
  nc -vz -G 5 100.115.212.72 "$port"
done
```

## 12. Mac RAG 健康检查

```powershell
# Win11 命令
Invoke-RestMethod `
  -Uri "http://100.68.157.108:18000/ready" `
  -TimeoutSec 180 |
Format-List
```

```bash
# Mac 命令
curl -fsS http://127.0.0.1:18000/ready | python3 -m json.tool
```

要求 `status=ready`，全部依赖 `pg`、`minio`、`milvus`、`embedding`、`reranker`、`authentication` 均为 `ok`。

## 13. Docker 健康检查

```powershell
Set-Location D:\law-rag-project
docker compose ps
```

要求以下容器均为 `healthy`：

| 容器 | 服务 |
|---|---|
| `law-platform-api` | Node.js 平台后端 |
| `law-platform-web` | React 前端 |
| `law-rag-kb` | Win11 旧 RAG |
| `law-rag-postgres` | PostgreSQL 16 |
| `law-rag-minio` | MinIO |
| `milvus-standalone` | Milvus 2.6 |
| `milvus-etcd` | Milvus 元数据 |

## 14. 常见故障判断

| 现象 | 可能原因 | 处理 |
|---|---|---|
| OA 打不开 | Tailscale 未连接 / Win11 Web 容器异常 | `tailscale status`、`docker compose ps` |
| 新文档 ingest 失败 | Mac Tailscale 不可达或 `/ready` 非 200 | Mac：`tailscale status`、`launchctl print`、`lsof -iTCP:18000`，Win11：`tailscale ping 100.68.157.108` |
| Mac `/ready` 某项非 ok | 对应 Win11 依赖端口不可达 | Mac：`nc -vz 100.115.212.72 5432/9000/19530`，Win11：`docker compose ps` |
| Tailscale ping 超时 | 某侧 Tailscale 断开或网络变化 | 两台机器均执行 `tailscale status`，确认 Connected |
| platform-api 配置未生效 | 改 `.env` 后未重建 | 执行 `docker compose up -d --no-deps --force-recreate platform-api` |
| 首次 ingest 走了旧 RAG | 路由模式被改回 `legacy`/`allowlist` | 检查 `RAG_DOCUMENT_ROUTE_MODE=initial_mac` |
| 局域网用户无法访问 OA | 未安装 Tailscale | 用 Win11 临时局域网 IP 访问（不写入文档），或安装 Tailscale |
| `/ready` 返回非 200 | 部分服务未就绪 | 等待 30s 重试；如持续失败，检查 Docker 容器状态和 Mac 依赖端口 |

## 15. 快速回滚

1. 保留当前根 `.env` 备份
2. 修改根 `.env`：

   ```text
   RAG_DOCUMENT_ROUTE_MODE=legacy
   RAG_DOCUMENT_MAC_ALLOWLIST=
   ```

3. 只重新创建平台后端：

   ```powershell
   docker compose up -d `
     --no-deps `
     --force-recreate `
     platform-api
   ```

说明：

- 只重建 platform-api，不重启数据库和向量库
- 回滚后普通新文档由 Win11 旧 RAG 处理
- 回滚不等于停用 Tailscale，两台机器间 Tailscale 连接不受影响
- 回滚前应备份 `.env`

## 16. 当前尚未开放的高级 Mutation

**允许**：

```text
普通新文档首次上传
force=false
由 Mac mini 处理
```

**暂不建议**：

```text
force=true
处理中替换原文件
复杂来源替换
promote
rebuild-sources
历史文档整体重建
```

原因：

- T03 源版本变化测试仍需补充
- T05 更新失败后的旧版本状态恢复尚未完全通过

当前状态**不是**"全部文档 Mutation 均已迁移到 Mac"。`mac` 模式（全量 Mutation 走 Mac）保留给完整迁移阶段。

## 17. 安全注意事项

- 不在本文档或任何 Markdown 中记录 Token、密码或密钥
- 不公开 18000、5432、9000、19530 到公网
- 不使用 Tailscale Funnel
- 不使用 Exit Node 作为本系统依赖
- 仅允许同一 tailnet 设备访问
- Win11 数据库、MinIO 和 Milvus 仍需保持现有主机防火墙和 Docker 监听限制
- Tailscale 地址固定，不代表应取消其他安全措施

## 18. 历史网络迁移记录

| 日期 | 变更说明 |
|---|---|
| 2026-07-31 | 局域网切换：Win11 更新为 `192.168.0.187`，Mac mini 更新为 `192.168.0.58`。Mac RAG 恢复监听 `0.0.0.0:18000`，platform-api 使用 `initial_mac` 模式，新文档首次 ingest 自动由 Mac mini 处理 |
| 2026-08-03 | 正式切换为 Tailscale 固定地址：Win11 `100.115.212.72`，Mac mini `100.68.157.108`。platform-api 通过 Tailscale 调用 Mac RAG，Mac 通过 Tailscale 连接 Win11 基础设施。项目不再依赖 `192.168.x.x` 局域网地址变化。OA 固定地址更新为 `http://100.115.212.72:5173` |
