# law-platform-web 法律 RAG 前端

React + TypeScript + Vite 构建的局域网验收前端，提供法条检索、带引用的知识问答和公共知识库上传管理。已登记文档默认每页 5 份，可选 5、10、20、50、100、500、1000；Markdown 与 Chunk 使用 React Router 独立页面并在新浏览器标签页打开。浏览器只调用相对地址 `/api/rag/*`；Docker 运行时由前端容器转发到 `platform-api`，本地开发时由 Vite 转发，不会直接访问 FastAPI、MinIO 或 Milvus，也不需要任何内部令牌。

上传区支持“单文件上传 / 批量导入”切换。批量模式一次最多选择 20 个文件，按选择顺序串行创建独立知识库文档，初始标题使用包含扩展名的完整文件名，并提供暂停、继续、停止后续任务和失败重试。批量结果及已登记文档均可修改标题；标题会立即用于检索和问答引用，但不会触发重新解析或向量化。

入库成功的文档提供“追加文件”和“管理文件”：后续原件加入同一 `doc_id`，原 Chunk 保留；源文件列表可逐个查看 Markdown/Chunk/耗时并单独安全替换。文档卡片显示全部有效来源中的最后上传时间，源文件管理显示每个来源自己的上传时间；新建、追加或替换成功会更新，重复上传、改标题、改分类和强制重建不会更新。

知识分类由数据库递归树驱动，不限制为两级。“分类管理”是顶部独立模块，地址为 `/knowledge/categories`，使用当前层级/下一级双栏和面包屑逐级维护分类；支持新增根/子分类、改名、别名、移动、同级排序、归档能力、敏感标记和安全停用。上传页只通过一级、二级、三级等动态选择框选择已有分类，不再提供分类管理操作；已有文档迁移集中在分类页面完成。“待分类”仅用于整理历史数据，不能用于新上传。当前可信局域网版本不显示逐份可见性确认；上传、追加、替换或移动完成后，包括敏感分类在内的资料都会自动供局域网检索。

回收站是顶部独立模块，地址为 `/knowledge/trash`。普通删除为纯软删除，原件、派生图片和向量都保留，可随时恢复；列表支持按标题搜索、按原分类筛选和按删除时间排序。恢复前前端先调用校验确认原件、图片和向量仍齐全，原分类已失效时需指定新分类；永久删除才会真正清理 MinIO 原件、Milvus 向量和派生图片，不可恢复。软删除、恢复和永久删除都只经过 `/api/rag/*`，不暴露内部端口。

## Docker 一键启动（推荐）

在项目根目录执行一次：

```powershell
cd D:\law-rag-project
docker compose up -d --build
docker compose ps
```

本机访问 `http://127.0.0.1:5173`。局域网设备访问 `http://服务器局域网IP:5173`；如果无法连接，只为专用网络放行 Windows 防火墙 TCP 5173。平台网关、FastAPI、数据库、Milvus 和 MinIO 不应对局域网开放。

Docker Desktop 开启“登录时启动”后，前端、平台 API、FastAPI 及基础设施会随 Docker 自动恢复，不需要再打开 PowerShell 分别启动。所有长期容器使用 `restart: unless-stopped`；如果手工停止过容器，执行 `docker compose up -d` 恢复。

## 本地开发模式（可选）

只有修改前端代码并需要热更新时才使用 Vite。先释放容器占用的 5173 和 3000：

```powershell
cd D:\law-rag-project
docker compose stop platform-web platform-api

cd D:\law-rag-project\law-platform-api
pnpm install
pnpm run start:dev
```

另开一个 PowerShell：

```powershell
cd D:\law-rag-project\law-platform-web
pnpm install
pnpm run dev
```

## 配置

Docker 容器固定通过内部服务名 `http://platform-api:3000` 转发，不需要前端环境变量。下面配置只用于本地 Vite 开发；只有平台 API 运行在其他本机地址时，才复制 `.env.example` 为 `.env.local` 并调整：

```dotenv
VITE_API_PROXY_TARGET=http://127.0.0.1:3000
```

任何以 `VITE_` 开头的变量都会进入前端环境，禁止在其中保存 `RAG_SERVICE_TOKEN`、数据库密码、MinIO 密钥或 Qwen API Key。

## 自动化测试

```powershell
pnpm run lint
pnpm run build
pnpm run test
pnpm run test:e2e
```

默认 Playwright 使用本机已安装的 Google Chrome 和模拟 API，仅验证电脑端布局，不调用 Qwen。真实 RAG 验收要求 FastAPI 与平台网关已启动，会调用真实检索、Reranker 和 Qwen：

如果 Docker 前端正在占用 5173，可让 Playwright 使用独立端口，避免复用旧容器页面：

```powershell
$env:PLAYWRIGHT_PORT='5174'
pnpm run test:e2e
Remove-Item Env:PLAYWRIGHT_PORT
```

```powershell
$env:REAL_RAG_E2E='1'
pnpm run test:e2e:real -- --project=desktop-chromium
Remove-Item Env:REAL_RAG_E2E
```

真实验收包括劳动合同法第二十条检索、民法典第一千二百零二条问答、无知识库依据时的拒答，以及公共工作资料的真实上传、自动入库和重复文件复用。模型回答措辞可以变化，但法条引用和拒答行为必须符合预期。

当前前端仅维护电脑端布局和桌面 Chromium 测试。历史桌面/手机验收结果保留在 `docs/` 报告中，不再作为当前支持范围。

完整架构、网关边界和真实测试结果见 [简单 RAG 前端与局域网测试报告](../docs/简单RAG前端与局域网测试报告_2026-07-15.md)。
上传、去重和自动入库详见 [公共知识库上传第一版实施报告](../docs/公共知识库上传第一版实施报告_2026-07-16.md)。

## 会话与安全边界

- 页面加载时生成一次 `session_id`，连续问答复用；刷新后生成新 ID。
- 不使用数据库或浏览器存储保存聊天历史。
- Markdown 不启用原始 HTML，因此模型回答中的 HTML/脚本不会作为页面代码执行。
- 知识库 Markdown 预览不加载内部 MinIO 图片 URL，浏览器仍只访问前端和平台网关。
- “查看 Markdown”和“查看 Chunk”仅在入库成功后可用，使用 `_blank` 与 `noopener noreferrer` 打开独立页面；原管理页的筛选、页码和滚动位置不受影响。
- 已登记文档分页可选 5、10、20、50、100、500、1000，默认 5；更改后回到第一页。Chunk 独立页仍为每页 20 条，两个分页互不影响。
- Chunk 正文使用纯文本渲染；Markdown 跳过原始 HTML，并用占位提示替代内部 MinIO 图片。
- Markdown 和 Chunk 默认合并全部来源，也可通过来源选择器只查看某一源文件。
- 处理过程中显示实时等待总时间；完成后以服务端记录的准确分阶段耗时替换。历史文档没有记录时不会伪造估算值。
- 当前版本适用于可信局域网验收，不包含登录；开放公网前必须增加登录、权限和正式反向代理。
