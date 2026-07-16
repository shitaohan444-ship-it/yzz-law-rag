# RAG 整体链路测试报告

> 最近更新：2026-07-15（修复后完整回归）  
> 结论：**通过**。完整证据和逐项命令见 [RAG完整回归测试报告_2026-07-15](RAG完整回归测试报告_2026-07-15.md)；后续历史数据闭环见 [RAG历史数据清理报告](RAG历史数据清理报告_2026-07-15.md)。

## 1. 当前验收状态

| 测试层 | 当前结果 |
|---|---:|
| Python 单元/API 契约 | 80/80 |
| 在线阶段测试 | 53/53 |
| 文档级检索 | Hit@1/3/5=15/15，MRR=1.000 |
| 法条级检索 | Hit@1/3/5=11/11，MRR=1.000 |
| Node ESLint | 0 errors / 0 warnings |
| Node build | 通过 |
| Node 单元测试 | 17/17 |
| Node HTTP E2E | 12/12 |

基础设施、迁移、文档解析、多模态、真实 LLM、引用、拒答、日志落库、附件/案件材料接口和持久层安全均通过。

## 2. 运行环境

- Python 3.11.9。
- Node.js 22.22.3，pnpm 10.32.0。
- PostgreSQL 16、MinIO、Milvus 2.6.19、etcd 和 `rag-api` 正常运行。
- `/health` 中 PostgreSQL/MinIO/Milvus 均为 `ok`。
- `/ready` 为 `ready`，Embedding/Reranker 均为 `ok`。
- Alembic current 与 heads 均为 `a1b2c3d4e5f6 (head)`。

## 3. 文档与多模态

23 个成功文档覆盖：TXT 6、Markdown 8、DOCX 5、PDF 2、PNG 2。旧 `.doc` 按预期跳过。

- 10 张图片全部 VL success。
- 9 张有检索价值的图片保留，1 张 Logo 过滤。
- 保留图片均有描述或 OCR。
- PostgreSQL/Milvus/聊天日志只保存稳定图片占位，预签名 URL 仅在 API 读取时生成。

## 4. 检索与问答

- Dense + sparse + RRF + bge-reranker 完整链路通过。
- 文档级 15 个问题全部 Top1。
- 法条级 11 个问题全部 Top1；产品责任的 5 种问法均优先返回民法典第一千二百零二条。
- 真实 Qwen 问答、连续引用、session_id、聊天日志一致性和无依据拒答均通过。
- 不存在文档的 ingest/markdown API 均返回安全 404；现有文档非 force 入库保持 200 skipped。

## 5. 当前性能

同一 5 个问题、同一模型和 `top_k=3`：

| 指标 | 结果 |
|---|---:|
| 顺序正确率 | 15/15 |
| 顺序 mean / P50 / P95 | 3.126s / 2.829s / 4.757s |
| 5 路正确率 | 5/5 |
| 5 路 wall / mean | 17.328s / 10.055s |
| 10 路正确率 | 10/10 |
| 10 路 wall / mean | 34.622s / 20.979s |

相对修复前基线，顺序 mean 改善约 44.7%，5 路 wall/mean 改善约 37.1%/38.5%，检索准确率未下降。

## 6. 数据和安全

- PostgreSQL：27 个文档记录，embedding success 23、failed 1、pending 1、skipped 2；23 个 success 全有非空 `body_markdown`。
- Milvus：198 chunks、23 个 doc_id，198/198 均为 `content_type=markdown`，旧 `:t:`/`:i:` 为 0。
- MinIO：32 个数据库有效对象引用逐个 stat，缺失 0。
- `kb_document`、图片表、附件表、Milvus 和 109 条聊天日志中 `X-Amz-*` 持久化命中均为 0。

## 7. 历史数据维护结果

获得明确授权后，文档 3、5、6、8、18 已按顺序逐个 force 重建，每个文档均保持 16 个 Markdown chunk。全库“节作为 chapter”、旧 `:t:`/`:i:` 和预签名 URL 均为 0。

清理后完整检索回归保持文档级 15/15、法条级 11/11，MRR 均为 1.000。该维护项已关闭。

## 8. 报告关系

- [RAG完整回归测试报告_2026-07-15](RAG完整回归测试报告_2026-07-15.md)：当前最终测试证据。
- [RAG问题修复报告_2026-07-15](RAG问题修复报告_2026-07-15.md)：根因、修改和修复前后对比。
- [RAG历史数据清理报告_2026-07-15](RAG历史数据清理报告_2026-07-15.md)：5 个历史文档逐个重建和清理后回归证据。
- [RAG全部功能测试报告_2026-07-15](RAG全部功能测试报告_2026-07-15.md)：修复前基线，保留原始问题数据。
- [RAG多模态手动测试报告_2026-07-14](RAG多模态手动测试报告_2026-07-14.md)：统一 Markdown 重构过程中的历史多模态证据。
