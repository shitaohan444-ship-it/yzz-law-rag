# 当事人材料智能起诉状（V3.2）

## 使用方式

1. 启动服务：`docker compose up -d --build document-renderer rag-api platform-api platform-web`。
2. 打开 `http://127.0.0.1:5173/drafting-lite`。
3. 从知识库“当事人案件材料/未结案、已结案”选择成功入库卷宗，也可补充上传 PDF、DOC 或 DOCX；两类材料合计不超过 10 份，临时文件总大小不超过 100 MB。
4. 案由保持“根据材料自动选择”，或从后端动态案由目录中手工指定。
5. 点击“分析材料并生成起诉状”。系统先执行与案由无关的公共当事人抽取，再自动生成 DOCX，正常流程不要求人工确认。

只有身份材料、无法判断法律关系时，页面仍会要求从当前动态案由目录中选择模板。主体字段直接检索知识库 chunk、Markdown 或上传材料；冲突时按照“用户修正 > 身份证/营业执照 > 事故认定书 > 案件基本信息页 > 起诉状 > 其他材料”自动仲裁。身份证号码确定时，性别和出生日期以身份证为准，证件类型默认填写“身份证”。无法确定的字段保留待补充提示，不中断生成。

## 独立接口

- `GET /api/drafting-lite/materials`：按标题、案件状态和分页列出可选知识库材料。
- `GET /api/drafting-lite/causes`：读取 Python 后端维护的案由目录；平台 API 和前端不维护案由白名单。
- `POST /api/drafting-lite/jobs`：`multipart/form-data`，字段为可选的 `files[]`、JSON 数组字符串 `knowledge_document_ids` 和 `cause`。
- `GET /api/drafting-lite/jobs/:jobId`：查询进度、案由、公共当事人结果、确认版本、问题、警告和下载地址。
- `POST /api/drafting-lite/jobs/:jobId/cause`：自动判断失败时提交人工案由。
- `POST /api/drafting-lite/jobs/:jobId/parties`：兼容旧任务的人工修正接口；新任务正常生成不依赖该接口。
- `GET /api/drafting-lite/jobs/:jobId/download`：下载生成的 DOCX。

公共当事人模块原生保存多个原告、多个被告和第三人，并保留逐字段材料来源、冲突候选和自动选择结果。当前单主体模板遇到多人结构时选择材料最完整、来源优先级最高的主体进行投影，同时在任务问题列表保留未投影主体信息。

知识库材料只读取已持久化的 Markdown 和 chunks，并在任务目录固化快照；不会重新下载原件或调用解析、OCR、VL、Embedding。解析结果会缓存，人工确认后恢复任务不会重复 OCR。该流程不读取或写入 OA 案件、证据、律师或审批数据。输入、输出及任务记录默认保留 24 小时；服务启动、创建任务或查询任务时会清理过期任务。

## 运行检查

```powershell
docker compose ps
docker compose logs --tail=100 rag-api platform-api platform-web document-renderer
```

四个服务应为 `healthy`。页面仅用于内部试运行；系统不会签名、盖章或向法院提交文书。
