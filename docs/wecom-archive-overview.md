# 企业微信聊天归档服务 — 整体情况

**服务器**：`root@120.27.160.118`（阿里云 ECS）<br>
**项目目录**：`/opt/wecom-msgaudit-archive`<br>
**报告时间**：2026-07-30 16:25 CST<br>
**状态**：✅ 长期运行中，每分钟自动归档，游标实时追平<br>
**访问方式**：公网 HTTPS + 密码 → `https://admin.jsyzz.com:18192/admin`（免隧道）

> 本文档为当前快照。部署/运维/卡死排查等完整细节见《企业微信归档管理后台使用指南.md》。

---

## 1. 当前运行数据

| 指标 | 数值 |
|---|---|
| 消息总数 | **7,689** 条（seq 1..7689，连续无缺口） |
| 消息状态 | **100% READY** |
| message.json OSS 对象 | 7,689 个，全部 **VERIFIED** |
| 媒体原件 OSS 对象 | **3,807** 个 **VERIFIED** + 2 个 **WAIVED** |
| 媒体类型分布 | file 3594 / image 177 / voice 31 / video 4 / emotion 3 |
| 群聊数 | **44** 个 |
| 未解决错误 | **0** |

> **WAIVED 媒体**：2 个无法下载的超大文件（`RicheeAI 1.6.1-arm64.zip` 软件安装包、`20260729_143651.m4a` 录音）。`GetMediaData` 对其挂起，已豁免移出下载队列，所属消息正文仍可读。详见使用指南 §8.6。

## 2. 游标

```
fetched_seq = 7,689
committed_seq = 7,689  ← 完全收敛，无积压
```

`fetched_seq = committed_seq` 表示**所有消息均已完整归档**（message.json + 媒体原件），无遗漏。每分钟增量拉取，0.6~5 秒完成一轮。

## 3. 访问方式（2026-07-30 起）

公网 HTTPS + 密码直连，免隧道：

```
https://admin.jsyzz.com:18192/admin   （账号 瀛之志 / 密码见服务器 htpasswd）
```

**链路**：公网 → 阿里云安全组 TCP 18192 → NPM 反代（HTTPS 解密 + Basic 密码校验）→ `wecom-archive-api:18190`（docker 内网，仅绑回环）。

三层防护：非常规端口 18192 + Basic 密码（apr1-MD5 哈希存储）+ HTTPS 加密（复用 admin.jsyzz.com 证书）。备用方式：SSH 隧道 `ssh -L 18190:127.0.0.1:18190 wecom-archive`。

## 4. OSS 存储

**Bucket**：`jsyzz-wecom-chatcontent-hz`（阿里云 OSS，杭州，**私有**）

| 对象类型 | 数量 | 路径模式 |
|---|---|---|
| message.json | 7,689 | `tenant/main/messages/year=YYYY/month=MM/day=DD/seq=N/msgid_hash={sha16}/message.json` |
| 媒体原件 | 3,807 | `tenant/main/media/year=YYYY/month=MM/day=DD/{room\|direct}/{h16}/seq=N/msgid_hash={sha16}/part=0_{sha16}.ext` |

- 路径中不出现姓名、聊天正文、手机号、原始 roomid、原始 conversation_key
- 每个对象携带 `x-oss-meta-sha256` / `x-oss-meta-msgid-hash` / `x-oss-meta-object-type` / `x-oss-meta-seq` 元数据
- 上传前 HEAD 预检 → sha256 比对 → 上传后核验，三重保障**绝不重复占用存储、绝不覆盖已有对象**

## 5. 系统组件

| 组件 | 运行方式 | 状态 |
|---|---|---|
| `wecom-archive.timer` | systemd timer，每分钟整点 | ✅ enabled + active |
| `wecom-archive.service` | systemd oneshot，timer 触发 | ✅ 每轮成功（0.6~5s） |
| `wecom-archive-api` | docker 容器，`127.0.0.1:18190` | ✅ 运行中（管理后台 + 签名 URL） |
| `nginx-proxy-manager` | docker 容器，`0.0.0.0:80,443,18192` | ✅ 公网反代（18192 → 归档后台） |
| PostgreSQL | docker 容器 `lawfirm-trial-server-postgres-1` | ✅ 运行中 |
| OSS 上传 | 阿里云 OSS 内网 endpoint | ✅ 可达 |

## 6. 完整数据流（每轮 A→K）

```
timer 每分钟触发
    │
    ▼
┌─ A. advisory lock 互斥（防并发双跑）───────────────┐
├─ B. GetChatData(fetched_seq) 拉取新加密消息         │ ← 从游标增量，绝不回 0
├─ C. 幂等落库（message + message_payload）           │   已存在则跳过，绝不覆盖
├─ D. DecryptData 解密 → normalize → 登记 media 任务  │
├─ E. 上传 message.json → OSS（HEAD 预检 + sha256）   │   同内容→ALREADY_VERIFIED
├─ F. GetMediaData 下载原件 → 上传 OSS                │   墙钟超时防大文件挂起
├─ G. 回填 verified_media_count → 置 READY            │   仅 json+媒体双齐才推进
├─ H. 连续区间推进 committed_seq（≤fetched_seq）      │   含缺口则止于缺口前
├─ I. 错误汇总（processing_error 未解决项）            │
├─ J. 输出 SUMMARY 日志                               │
└─ K. 释放 advisory lock                              │
```

> **步骤 F 关键保护**：`GetMediaData` 下载单个媒体有墙钟超时 `MEDIA_WALL_TIMEOUT`（默认 180s），超时即放弃该媒体继续下一个，防止超大文件挂起卡死整轮（2026-07-30 根治，见使用指南 §8.6）。

## 7. 安全设计

| 层面 | 措施 |
|---|---|
| AccessKey/Secret/私钥 | 仅通过 **0400 权限文件**挂载进容器，绝不写进代码/镜像/日志/环境变量 |
| 日志输出 | 只输出 seq / 计数 / object_key / sha16 维度；**绝不输出**聊天正文、完整 sdkfileid、CorpID、Secret、私钥、encrypt_random_key、encrypt_chat_msg |
| OSS Bucket | **私有**（非 public-read），业务系统通过**临时签名 URL** 访问 |
| 签名 URL | 仅对 `VERIFIED` 对象签发；默认 600s 过期（钳制 [60, 3600]）；仅监听 `127.0.0.1` |
| 公网访问 | NPM 反代 18192：HTTPS + Basic 密码（apr1-MD5 哈希）+ 非常规端口 |
| 路径脱敏 | roomid / conversation_key 均以 sha256 前 16 位入路径，不出现原始值 |
| 并发安全 | `pg_try_advisory_lock` 防多实例同时运行；timer 重叠触发自动 SKIP |
| 数据不可变 | 幂等逻辑只在首次写入时 INSERT/UPDATE；后续重入仅校验一致性，绝不覆盖 |
| 媒体下载 | 墙钟超时防挂起；无法下载的文件标 `WAIVED` 移出队列 |

## 8. 关键里程碑

| 时间 | 事件 |
|---|---|
| 2026-07-24 | 12 阶段验收全通，长期运行（详见使用指南 §8 历史） |
| 2026-07-30 | **公网 HTTPS+密码访问上线**（NPM 反代 18192，免隧道） |
| 2026-07-30 | **修复前端 API base bug**（硬编码 :18190 → 同源，解决公网"加载失败"） |
| 2026-07-30 | **根治 GetMediaData 大文件挂起卡死归档**（墙钟超时 + 毒文件 WAIVED 豁免），补回 7/28~7/30 积压的 1700+ 条消息 |

## 9. 日常运维速查

```bash
# 看最近几轮运行情况
journalctl -u wecom-archive.service -n 30 --no-pager

# 看游标是否在推进（fetched=committed 且持续增长）
export PGPASSWORD="$(cat /opt/wecom-msgaudit-archive/secrets/db_password)"
docker exec -e PGPASSWORD="$PGPASSWORD" lawfirm-trial-server-postgres-1 \
  psql -U lawfirm_trial -d lawfirm_system_trial -c \
  "SELECT fetched_seq, committed_seq, (fetched_seq=committed_seq) AS consistent
   FROM wecom_archive.archive_cursor c JOIN wecom_archive.tenant t ON t.id=c.tenant_id
   WHERE tenant_code='main';"

# 手动触发一轮（不等下一分钟）
systemctl start wecom-archive.service

# 媒体/消息状态分布（查是否有卡在 RETRY_WAIT 的毒文件）
docker exec -e PGPASSWORD="$PGPASSWORD" lawfirm-trial-server-postgres-1 \
  psql -U lawfirm_trial -d lawfirm_system_trial -c \
  "SELECT processing_status, COUNT(*) FROM wecom_archive.media GROUP BY 1;
   SELECT processing_status, COUNT(*) FROM wecom_archive.message GROUP BY 1;"
```

> **归档卡死（页面不更新、反复 ARCHIVE_SKIP）排查与恢复**：见《企业微信归档管理后台使用指南.md》§8.6。

---

**结论**：7,689 条消息 + 3,807 个媒体原件全部归档至私有 OSS，游标完全收敛（fetched=committed=7689），systemd timer 每分钟增量运行，0 错误 0 积压。公网 HTTPS+密码访问可用，大文件下载已有墙钟超时保护，不再卡死。电脑关机不影响，服务器独立运转。
