# 法律法规官网链接维护手册

## 边界

- 仅关联“法律法规”分类树中的知识库文档。
- 只写 `oa.legal_regulation_catalog`、`oa.kb_document_regulation_link`、
  `oa.legal_regulation_import_run`。
- 不调用 ingest，不修改文档状态、Chunk、MinIO或Milvus。
- 搜索和问答仍由Win11 `rag-api`处理，Mac文档导入链路不变。

## 配置

```dotenv
RAG_OFFICIAL_LINKS_ENABLED=false
```

迁移、dry-run和灰度映射验收完成前保持 `false`。启用或回滚该开关只需重建
`rag-api`：

```powershell
docker compose up -d --no-deps --force-recreate rag-api
```

## 导入

先构建迁移镜像：

```powershell
docker compose build db-migrate
```

dry-run（零数据库写入）：

```powershell
docker compose run --rm --no-deps `
  -v "<CSV绝对路径>:/input/regulations.csv:ro" `
  -v "<报告目录绝对路径>:/reports" `
  db-migrate python scripts/import_legal_regulation_catalog.py `
  --csv /input/regulations.csv `
  --dry-run `
  --report /reports/legal-regulation-dry-run.json
```

灰度文档：

```powershell
docker compose run --rm --no-deps `
  -v "<CSV绝对路径>:/input/regulations.csv:ro" `
  -v "<报告目录绝对路径>:/reports" `
  db-migrate python scripts/import_legal_regulation_catalog.py `
  --csv /input/regulations.csv `
  --apply `
  --document-ids "101,102,103" `
  --report /reports/legal-regulation-gray.json
```

全量映射：

```powershell
docker compose run --rm --no-deps `
  -v "<CSV绝对路径>:/input/regulations.csv:ro" `
  -v "<报告目录绝对路径>:/reports" `
  db-migrate python scripts/import_legal_regulation_catalog.py `
  --csv /input/regulations.csv `
  --apply `
  --report /reports/legal-regulation-full.json
```

只有在目录下线已经过人工确认时才加入 `--deactivate-missing`。默认只报告CSV中
缺失的旧目录项，不停用。

## 验收

1. 检查报告中的目录行数、六个分类、重复组、元数据失败和未关联文档。
2. 未关联原因必须人工判断；日期并列时不得按CSV顺序猜测。
3. 搜索结果和问答引用只在存在有效映射时显示“官网最新版”。
4. 链接必须为 `https://flk.npc.gov.cn/detail?id=<32位十六进制ID>`。
5. 对比导入前后的文档、来源、附件、Milvus行数和MinIO对象数。

## 回滚

首选关闭展示，不删除数据：

```dotenv
RAG_OFFICIAL_LINKS_ENABLED=false
```

```powershell
docker compose up -d --no-deps --force-recreate rag-api
```

代码回滚时，将 `rag-api`、`platform-api`、`platform-web` 恢复到部署前的
`rollback-official-links-<时间戳>` 镜像。三张新增表可以保留，旧代码不会读取。

若某次映射批次有误，先关闭开关并备份数据库，再按运行ID移除仍属于该批次的映射：

```sql
DELETE FROM oa.kb_document_regulation_link
WHERE linked_run_id = :import_run_id;
```

该语句不会删除目录、文档、Chunk或向量；如需恢复上一批映射，应使用对应导入报告
重新执行上一份CSV/灰度清单，而不是手工猜测目录项。
