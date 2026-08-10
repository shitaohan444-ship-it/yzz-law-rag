# 法律文书模板治理

- `D:\law-rag-project\要素式模板` 是当前 originals 基线，只读使用；编译器不得原地改写。
- 每次审计输出 SHA-256、原始格式、表格数、合并标记、勾选符号和结构统计到 `artifacts/legal-drafting/`。
- `normalized/` 只保存编译后的工作副本；首批激活模板必须有人工确认的 sidecar schema 与 compiler report。
- 两份 `ole_doc` 资产不得直接交给 `python-docx`，须在受控 LibreOffice 转换后重新登记 hash 和格式。
- 模板状态只有在技术与法律负责人共同确认后才能变为 `active`。
- 民间借贷起诉状 sidecar 已包含 25 个字段、6 个区块和 1 个重复组，作为首个 active 技术基线。
- 侵害商标权纠纷答辩状 sidecar 已包含答辩事项、己方证据和逐项质证字段，以及 2 个重复组；在完成金标准和法律确认前保持 `draft`，不得由匹配接口自动选中。
