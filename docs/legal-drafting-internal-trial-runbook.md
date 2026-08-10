# 多 Agent 法律文书内部试运行手册

本手册仅适用于隔离局域网内的固定开发律师身份。系统输出始终是“AI 草稿，须经律师审核”，不得自动签名、盖章或提交法院。

## 1. 首次配置

1. 在根目录 `.env` 设置三个不少于 32 字符的随机值：`LEGAL_DRAFTING_WORKER_TOKEN`、`LEGAL_DRAFTING_RUN_TOKEN_SECRET`、`LEGAL_DRAFTING_RENDERER_TOKEN`。
2. 在 `law-rag-kb/.env` 配置百炼文本模型和视觉模型凭证；文本模型为 `qwen3.7-plus`，视觉模型为 `qwen3-vl-plus`。
3. 启动 PostgreSQL 并执行 Alembic 迁移。
   迁移完成后在 `law-platform-api` 执行 `pnpm prisma db pull` 和 `pnpm prisma:generate`；Alembic 仍是唯一迁移权威。
4. 使用 `scripts/configure-agent-runtime-role.ps1` 创建仅能访问 `agent_runtime` schema 的角色。
5. 把该角色连接串写入根目录 `.env` 的 `AGENT_DATABASE_URL`，并带上 `search_path=agent_runtime,public`。
6. 仅在准备治理两份旧 OLE 模板时，于安装 LibreOffice 的受控环境运行 `scripts/convert-legacy-legal-templates.ps1`；脚本会校验原件 hash、转换格式和超时，并只写 normalized 副本。

示例（密码仅为参数位置示意，不要把真实密码写入仓库）：

```powershell
.\scripts\configure-agent-runtime-role.ps1 `
  -AgentUser law_agent_runtime `
  -AgentPassword '<独立强密码>' `
  -AdminPassword '<数据库管理员密码>'
```

## 2. 启动与检查

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

必须确认：数据库迁移成功、平台 API 健康、渲染器健康、Worker 持续运行且没有凭证或 checkpoint 错误。平台 API、RAG、PostgreSQL、MinIO 和前端均只绑定 `127.0.0.1`；Worker 与渲染器不发布宿主机端口。

## 3. 试运行流程

1. 在“文书协作”选择案件、材料、证据及法律知识文档白名单。
2. 核对模板匹配结果；低置信或多候选必须人工确认。
3. 对缺失、冲突值逐项查看材料、页码和置信度后确认。
4. 生成完成后检查结构化正文、PDF、来源、五类审校问题和版本记录。
5. 律师通过会生成新的 `lawyer_approved` 版本，不覆盖 AI 版本；退回会保留审核意见和退回状态。
6. 下载产物前再次确认页数、残留占位符、空白页、文字截断和表格错位。

## 4. 故障处理

- Worker 崩溃：保留任务，不手工改业务状态；租约过期后由另一 Worker 从 PostgreSQL checkpoint 恢复。
- 扫描件无法识别：检查百炼 VL 配置；系统会阻断需要 OCR/VL 的扫描材料，不静默忽略。
- RAG 无依据：补充或修正当前 run 的知识文档白名单后恢复；不得让模型凭记忆补写法条。
- 渲染失败：查看 renderer report；残留占位符、空白页和字体替代均不得绕过。
- 跨案件或伪造 token：立即停止试运行，保留 generation event 和平台日志用于审计。

## 5. 质量门

进入内部试运行前，必须完成 20 个脱敏民间借贷金标准样本，并达到计划书中的来源覆盖、法条可核验、证据一致、越权检索、恢复成功率及视觉回归指标。第二模板通过前不得批量激活其余模板。
