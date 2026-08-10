# Mac mini RAG 局域网运维

本文档是 Win11 主机 + Mac mini 纯局域网双机部署的唯一运维口径。涉及普通用户操作时，请只用 OA 前端；本文所有后端接口均不对普通用户开放。

## 1. 当前系统用途

系统用于律师事务所知识库文档的上传、解析、向量化和智能检索。新文档的解析和向量化由 Mac mini 协处理，其余检索、问答和高级数据操作由 Win11 主机上的旧 RAG 提供。

## 2. 当前局域网地址

| 角色 | 局域网地址 | 说明 |
|---|---|---|
| Win11 主机 | `192.168.2.190` | 前端、平台后端、旧 RAG、PostgreSQL、MinIO、Milvus |
| Mac mini | `192.168.2.6` | 新文档解析、切片、向量化协处理 |
| OA 局域网地址 | `http://192.168.2.190:5173` | 同一局域网设备可用 |
| Mac RAG 服务 | `http://192.168.2.6:18000` | 后端接口，**非普通用户操作页面** |
| Win11 旧 RAG（内部） | `http://rag-api:8000` | Docker 内网地址，仅供平台后端调用 |

当前运行配置：

```text
RAG_DOCUMENT_API_BASE_URL=http://192.168.2.6:18000
RAG_DOCUMENT_ROUTE_MODE=initial_mac
RAG_DOCUMENT_MAC_ALLOWLIST=         # 为空
LawRagImportBridge=Disabled
```

## 3. OA 访问地址

```text
http://192.168.2.190:5173
```

这是普通用户的操作入口。浏览器只访问前端，由前端容器经 Docker 内网转发到平台后端，不直连任何数据库或 RAG 服务。该地址只在当前局域网内有效。

## 4. Mac RAG 服务地址

```text
http://192.168.2.6:18000
```

**仅由 Win11 platform-api 调用，不是普通用户操作页面**。提供 `/health`、`/ready` 和文档 ingest 接口。监听 `0.0.0.0:18000`，platform-api 通过局域网地址访问。

## 5. 当前处理架构

```text
OA 上传新知识库文档
→ Win11 platform-api
→ 通过局域网调用 Mac mini（http://192.168.2.6:18000）
→ Mac mini 解析文档
→ Mac mini 按 Markdown 结构切片
→ Mac mini 用 BGE-M3 + MPS 生成 Dense/Sparse 向量
→ 通过局域网写入 Win11 Milvus（192.168.2.190:19530）
→ 更新 Win11 PostgreSQL 状态（192.168.2.190:5432）
→ Win11 旧 RAG 继续提供搜索、聊天和文档读取
```

Mac mini 不持有数据，只负责计算；原始文件、向量、状态最终都落在 Win11 的 MinIO、Milvus 和 PostgreSQL 中。

### Mac 依赖 Win11 基础设施

```text
Mac RAG
→ Win11 PostgreSQL：192.168.2.190:5432
→ Win11 MinIO     ：192.168.2.190:9000
→ Win11 Milvus    ：192.168.2.190:19530
```

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

**重要**：Mac 失败时不得自动回退 Win11 旧 RAG 处理首次 ingest。

## 7. Win11 重启后的检查

```powershell
Set-Location D:\law-rag-project

docker compose ps

Test-NetConnection `
  -ComputerName 192.168.2.6 `
  -Port 18000

Invoke-RestMethod `
  -Uri "http://192.168.2.6:18000/ready" `
  -TimeoutSec 180 |
Format-List

docker compose exec -T platform-api `
  printenv RAG_DOCUMENT_API_BASE_URL

docker compose exec -T platform-api `
  printenv RAG_DOCUMENT_ROUTE_MODE

docker compose exec -T platform-api `
  printenv RAG_DOCUMENT_MAC_ALLOWLIST
```

正确结果：

```text
RAG_DOCUMENT_API_BASE_URL=http://192.168.2.6:18000
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

1. 启动 Docker Desktop
2. 进入 `D:\law-rag-project`
3. 执行 `docker compose up -d`
4. 执行 `docker compose ps`
5. 检查 Mac `/ready`
6. 确认 route mode 仍为 `initial_mac`
7. 不需要修改配置，除非 IP 发生变化

## 8. Mac mini 重启后的检查

```bash
for port in 5432 9000 19530; do
  nc -vz -G 5 192.168.2.190 "$port"
done

launchctl print gui/$(id -u)/com.yzz.law-rag-kb |
grep -E 'state =|pid =|last exit code'

lsof -nP -iTCP:18000 -sTCP:LISTEN

curl -fsS http://127.0.0.1:18000/ready |
python3 -m json.tool

curl -fsS http://192.168.2.6:18000/ready |
python3 -m json.tool
```

正确结果：

```text
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
2. 检查 LaunchAgent：

```bash
launchctl print gui/$(id -u)/com.yzz.law-rag-kb | grep 'state ='
```

3. 必要时执行：

```bash
launchctl kickstart -k gui/$(id -u)/com.yzz.law-rag-kb
```

4. 检查 `127.0.0.1:18000/ready`
5. 检查 `192.168.2.6:18000/ready`

## 9. Docker 启动顺序

Win11 Docker 容器通过 `restart: unless-stopped` 自动恢复。首次启动或停止后恢复：

```powershell
Set-Location D:\law-rag-project
docker compose up -d
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

## 10. 局域网连通性检查

### Win11 → Mac

```powershell
Test-NetConnection -ComputerName 192.168.2.6 -Port 18000
ping 192.168.2.6
```

### Mac → Win11

```bash
for port in 5432 9000 19530; do
  nc -vz -G 5 192.168.2.190 "$port"
done
ping -c 4 192.168.2.190
```

## 11. Mac RAG 健康检查

```powershell
# Win11 命令
Invoke-RestMethod `
  -Uri "http://192.168.2.6:18000/ready" `
  -TimeoutSec 180 |
Format-List
```

```bash
# Mac 命令
curl -fsS http://127.0.0.1:18000/ready | python3 -m json.tool
```

要求 `status=ready`，全部依赖 `pg`、`minio`、`milvus`、`embedding`、`reranker`、`authentication` 均为 `ok`。

## 12. 常见故障判断

| 现象 | 可能原因 | 处理 |
|---|---|---|
| OA 打不开 | 5173 端口不可达 / 前端容器异常 | 核对 Win11 IP、放行防火墙 TCP 5173、`docker compose ps` |
| 新文档 ingest 失败 | Mac 不可达或 `/ready` 非 200 | 检查 Mac LaunchAgent、18000 监听、Win11 依赖端口 |
| Mac `/ready` 某项非 ok | 对应 Win11 依赖（PG/MinIO/Milvus）异常 | Win11 `docker compose ps` 确认基础设施 healthy |
| platform-api 配置未生效 | 改 `.env` 后未刷新容器环境 | `docker compose stop platform-api && docker compose rm -f platform-api && docker compose up -d --no-build platform-api`（**不要**用 `--force-recreate`，会触发 rebuild） |
| 首次 ingest 走了旧 RAG | 路由模式被改回 `legacy`/`allowlist` | 核对 `RAG_DOCUMENT_ROUTE_MODE=initial_mac` |
| 局域网不通 | IP 变化或不在同一网络 | `ping` 两台机器互测，检查路由器 |
| `/ready` 返回非 200 | 部分服务未就绪 | 等待 30s 重试；如持续失败，检查 Docker 容器和 Mac 依赖端口 |

## 13. IP 变化后的处理步骤

1. 查询 Win11 和 Mac 的新 IP
2. 确认两台设备处于同一局域网
3. Mac 测试 Win11 的 `5432`、`9000`、`19530` 端口：

   ```bash
   for port in 5432 9000 19530; do
     nc -vz -G 5 <新Win11 IP> "$port"
   done
   ```

4. 更新 Mac `.env` 中的：

   ```text
   POSTGRES_HOST=<新Win11 IP>
   MINIO_ENDPOINT=<新Win11 IP>
   MILVUS_HOST=<新Win11 IP>
   TRUSTED_HOSTS=<新Win11 IP>,<新Mac IP>,...
   ```

5. 重启 Mac LaunchAgent：

   ```bash
   launchctl kickstart -k gui/$(id -u)/com.yzz.law-rag-kb
   ```

6. 确认 Mac `/ready` 返回 200
7. 更新 Win11 根 `.env` 中的：

   ```text
   RAG_DOCUMENT_API_BASE_URL=http://<新Mac地址>:18000
   ```

8. 只重新创建 platform-api（**用现有镜像，不要重新 build 代码**）：

   ```powershell
   docker compose stop platform-api
   docker compose rm -f platform-api
   docker compose up -d --no-build platform-api
   ```

   > **注意**：`RAG_DOCUMENT_API_BASE_URL` 是运行时从根 `.env` 注入的环境变量，不打进镜像。因此改 IP 只需刷新容器环境，**无需也不应**重新 build。
   > **不要**用 `docker compose up -d --force-recreate platform-api`：`docker-compose.yml` 中 platform-api 配置了 `pull_policy: build`，该命令会触发完整代码 rebuild（`pnpm run build`），耗时且可能失败。`--no-build` 可强制复用现有镜像。

9. **不要**重启 PostgreSQL、MinIO、Milvus 和旧 RAG
10. 再次验证容器内部访问 Mac 成功：

   ```powershell
   docker compose exec -T platform-api printenv RAG_DOCUMENT_API_BASE_URL
   ```

## 14. DHCP 静态租约配置要求

为避免 IP 变化后需手动更新配置，建议在路由器中为两台机器配置 DHCP 静态租约：

| 设备 | 固定 IP | 绑定方式 |
|---|---|---|
| Win11 | `192.168.2.190` | 绑定实际使用网卡的 MAC 地址 |
| Mac mini | `192.168.2.6` | 绑定实际使用网卡的 MAC 地址 |

如果没有 DHCP 静态租约，路由器重新分配 IP 后仍需按第 13 节步骤修改两端配置。

## 15. 快速回滚方式

1. 保留当前根 `.env` 备份
2. 修改根 `.env`：

   ```text
   RAG_DOCUMENT_ROUTE_MODE=legacy
   RAG_DOCUMENT_MAC_ALLOWLIST=
   ```

3. 只重新创建（用现有镜像，不 rebuild）：

   ```powershell
   docker compose stop platform-api
   docker compose rm -f platform-api
   docker compose up -d --no-build platform-api
   ```

说明：

- 只重建 platform-api
- 不重启 PostgreSQL、MinIO、Milvus
- 回滚后普通新文档由 Win11 旧 RAG 处理
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

当前状态**不是**"全部高级 Mutation 已迁移到 Mac"。`mac` 模式保留给完整迁移阶段。

## 17. Tailscale 历史说明

- Tailscale 曾于 2026-08-03 短暂用于解决局域网 IP 变化问题
- 当前生产系统已切回纯局域网通信
- Tailscale 不再作为 platform-api 与 Mac RAG 之间的正式通信路径
- Mac 不再通过 Tailscale 连接 PostgreSQL、MinIO 和 Milvus
- Tailscale 迁移过程完整保留在 [Mac mini RAG Tailscale 运维（历史）](Mac-mini-RAG-Tailscale运维.md)
- 历史验收报告中的 Tailscale 地址保持不变

## 18. 安全注意事项

- 不在本文档或任何 Markdown 中记录 Token、密码或密钥
- 不公开 18000、5432、9000、19530 到公网
- OA 和 Mac RAG 只在当前局域网内可访问
- 离开当前局域网后系统默认不可远程访问
- Win11 数据库、MinIO 和 Milvus 保持现有主机防火墙和 Docker 监听限制
- 不在正文中引用 Tailscale 地址作为当前生产地址

## 历史变更

- 2026-07-31：局域网切换，Win11 地址更新为 `192.168.0.187`，Mac mini 地址更新为 `192.168.0.58`，Mac RAG 恢复监听 `0.0.0.0:18000`，platform-api 使用 `initial_mac` 模式
- 2026-08-03：短暂切换为 Tailscale 固定地址（Win11 `100.115.212.72`、Mac `100.68.157.108`），随后切回纯局域网通信。当时 Win11 地址为 `192.168.2.190`，Mac mini 地址为 `192.168.2.173`
- 2026-08-10：更换网络，**Mac mini 地址由 `192.168.2.173` 变为 `192.168.2.6`，Win11 保持 `192.168.2.190`**。Mac `.env` 三个依赖（POSTGRES/MILVUS/MINIO）由旧 `192.168.0.127` 改为 `192.168.2.190`，`TRUSTED_HOSTS` 追加 `192.168.2.6`；Win11 根 `.env` `RAG_DOCUMENT_API_BASE_URL` 改为 `http://192.168.2.6:18000`。platform-api 用 `stop + rm + up --no-build` 重建（`--force-recreate` 会触发 rebuild）。两端 `/ready`、`/health` 全部 200，链路验证通过。
