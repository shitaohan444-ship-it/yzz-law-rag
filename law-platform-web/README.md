# law-platform-web 法律 RAG 前端

React + TypeScript + Vite 实现的局域网验收前端，提供法条检索、带引用的知识问答和公共知识库上传管理。已登记文档每页显示 5 份；Markdown 与 Chunk 使用 React Router 独立页面并在新浏览器标签页打开。浏览器只调用相对地址 `/api/rag/*`，由 Vite 转发到 `law-platform-api`；不会直接访问 FastAPI、MinIO 或 Milvus，也不需要任何内部令牌。

顶部上传表单支持提交前“重新选择文件”和“清除”，只负责新建独立知识库。入库成功的文档提供“追加文件”和“管理文件”：后续原件加入同一 `doc_id`，原 Chunk 保留；源文件列表可逐个查看 Markdown/Chunk/耗时并单独安全替换。

## 启动顺序

1. 在项目根目录启动 Docker 基础设施与 FastAPI：

   ```powershell
   cd D:\law-rag-project
   docker compose up -d
   Invoke-RestMethod http://127.0.0.1:8000/ready
   ```

2. 启动平台网关：

   ```powershell
   cd D:\law-rag-project\law-platform-api
   pnpm install
   pnpm run start:dev
   ```

3. 启动前端：

   ```powershell
   cd D:\law-rag-project\law-platform-web
   pnpm install
   pnpm run dev
   ```

本机访问 `http://127.0.0.1:5173`。局域网设备访问 `http://服务器局域网IP:5173`；如果无法连接，只为专用网络放行 Windows 防火墙 TCP 5173。平台网关、FastAPI、数据库、Milvus 和 MinIO 不应对局域网开放。

## 配置

默认代理目标是 `http://127.0.0.1:3000`。只有平台 API 运行在其他本机地址时，才复制 `.env.example` 为 `.env.local` 并调整：

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

默认 Playwright 使用本机已安装的 Google Chrome 和模拟 API，覆盖桌面及手机布局，不调用 Qwen。真实 RAG 验收要求 FastAPI 与平台网关已启动，会调用真实检索、Reranker 和 Qwen：

```powershell
$env:REAL_RAG_E2E='1'
pnpm run test:e2e:real -- --project=desktop-chromium
Remove-Item Env:REAL_RAG_E2E
```

真实验收包括劳动合同法第二十条检索、民法典第一千二百零二条问答、无知识库依据时的拒答，以及公共工作资料的真实上传、自动入库和重复文件复用。模型回答措辞可以变化，但法条引用和拒答行为必须符合预期。

2026-07-16 当前验收基线：组件测试 7/7、模拟浏览器测试 6/6（桌面 + 手机）、真实 RAG 检索/问答/拒答 6/6（桌面 + 手机）及真实上传 1/1（桌面串行），lint 与 build 均通过。模拟浏览器已覆盖 Chunk/Markdown 互斥、metadata、耗时展开、手机布局、无横向溢出，以及不直连 8000、9000、19530。

多源文件追加完成后，组件测试为 9/9、模拟浏览器为 6/6。桌面和手机真实页面额外验证文档 #38 的 2 个来源、来源筛选、Chunk 预览、响应式弹窗和内部端口隔离。页面不再显示容易误解的“继续上传”；顶部按钮为“新建并自动入库”，已入库卡片使用“追加文件”。

五条分页与独立预览完成后，组件测试更新为 14/14，模拟浏览器保持 6/6，真实文档 #38 桌面/手机新标签页验收 2/2。独立地址为 `/knowledge/documents/{id}/markdown` 和 `/knowledge/documents/{id}/chunks`；单来源使用 `source_id`，Chunk 页同时使用 `page` 保存页码。返回链接 `/?tab=knowledge` 会直接打开知识库管理标签。

完整架构、网关边界和真实测试结果见 [简单 RAG 前端与局域网测试报告](../docs/简单RAG前端与局域网测试报告_2026-07-15.md)。
上传、去重和自动入库详见 [公共知识库上传第一版实施报告](../docs/公共知识库上传第一版实施报告_2026-07-16.md)。

## 会话与安全边界

- 页面加载时生成一次 `session_id`，连续问答复用；刷新后生成新 ID。
- 不使用数据库或浏览器存储保存聊天历史。
- Markdown 不启用原始 HTML，因此模型回答中的 HTML/脚本不会作为页面代码执行。
- 知识库 Markdown 预览不加载内部 MinIO 图片 URL，浏览器仍只访问前端和平台网关。
- “查看 Markdown”和“查看 Chunk”仅在入库成功后可用，使用 `_blank` 与 `noopener noreferrer` 打开独立页面；原管理页的筛选、页码和滚动位置不受影响。
- 已登记文档每页 5 份；Chunk 独立页仍为每页 20 条，两个分页互不影响。
- Chunk 正文使用纯文本渲染；Markdown 跳过原始 HTML，并用占位提示替代内部 MinIO 图片。
- Markdown 和 Chunk 默认合并全部来源，也可通过来源选择器只查看某一源文件。
- 处理过程中显示实时等待总时间；完成后以服务端记录的准确分阶段耗时替换。历史文档没有记录时不会伪造估算值。
- 当前版本适用于可信局域网验收，不包含登录；开放公网前必须增加登录、权限和正式反向代理。
