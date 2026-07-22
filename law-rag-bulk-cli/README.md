# DOCX 后台断点续传导入工具

这是独立的服务器端命令行工具，不提供网页入口，也不会常驻运行。任务状态默认保存在
`D:\law-rag-bulk-data\bulk-import.sqlite3`，上传和 RAG 入库必须分别执行。

## 安装

```powershell
cd D:\law-rag-project\law-rag-bulk-cli
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e .
```

## 正式使用流程（本轮验收不要执行）

```powershell
# 1. 查看可归档分类
law-rag-bulk --api-url http://127.0.0.1:3000 categories

# 2. 创建任务并扫描 DOCX；一个任务只能绑定一个分类
law-rag-bulk --api-url http://127.0.0.1:3000 create --source D:\待导入法规 --category-id 123

# 3. 仅上传 MinIO 并登记数据库，不会调用 RAG
law-rag-bulk upload --job <任务ID>

# 4. 核对状态与报告
law-rag-bulk status --job <任务ID>
law-rag-bulk report --job <任务ID>

# 5. 人工确认后，显式启动 RAG；Qwen 摘要和图片分析固定关闭
law-rag-bulk ingest --job <任务ID> --confirm
```

失败项使用 `retry --stage upload|ingest` 重置后，再重新执行相应阶段。上传过程中中断后，
下次启动会把未完成的 `uploading` 恢复为 `ready`；入库中断会恢复为 `uploaded`。

`source_relative_path` 发送的是包含文件名的相对路径。平台据此生成：

```text
knowledge-base/<分类路径>/<源相对目录>/<原文件名.docx>
```

对象文件名不会增加日期、ID、UUID 或哈希；若超过 MinIO 单路径段安全长度，只截短文件名，
数据库中的标题和原文件名仍保持完整。同一路径已有不同内容时返回冲突，绝不覆盖。
