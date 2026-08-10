from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

from docx import Document


def set_paragraph_text(paragraph, value: str) -> None:
    if paragraph.runs:
        paragraph.runs[0].text = value
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(value)


def set_cell(cell, value: str) -> None:
    set_paragraph_text(cell.paragraphs[0], value)
    for paragraph in cell.paragraphs[1:]:
        set_paragraph_text(paragraph, "")


def replace_exact(document: Document, mapping: dict[str, str]) -> None:
    for paragraph in document.paragraphs:
        if paragraph.text in mapping:
            set_paragraph_text(paragraph, mapping[paragraph.text])
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if paragraph.text in mapping:
                        set_paragraph_text(paragraph, mapping[paragraph.text])


def replace_table(table, rows: list[list[str]]) -> None:
    while len(table.rows) < len(rows):
        table._tbl.append(deepcopy(table.rows[-1]._tr))
    while len(table.rows) > len(rows):
        table._tbl.remove(table.rows[-1]._tr)
    for row, values in zip(table.rows, rows, strict=True):
        while len(row.cells) < len(values):
            raise ValueError("reference table does not have enough columns")
        for cell, value in zip(row.cells, values, strict=False):
            set_cell(cell, value)


def main(source: str, output: str) -> None:
    document = Document(source)
    document.core_properties.title = "多智能体协同撰写要素式法律文书——详细设计与实施计划书 V2.0"
    document.core_properties.subject = "law-rag-project 受控多 Agent 法律文书生成实施基线"
    document.core_properties.comments = "V2.0：固定 Worker、Checkpoint、模板治理、法律研究、五类审校和独立渲染方案。"

    replace_exact(
        document,
        {
            "模板数量、文件格式和表格结构基于本次提供的“要素式模板(1).zip”进行初步自动检查。": "模板数量、文件格式和表格结构基于 D:\\law-rag-project\\要素式模板 的完整资产审计结果：共 113 份，其中 111 份为标准 OOXML DOCX，2 份为旧版二进制 DOC；单份模板包含 1—7 个表格。",
            "推荐技术结论：将 LangGraph 安装和运行在 law-rag-kb 中，目录位于 D:\\law-rag-project\\law-rag-kb\\app\\workflows\\legal_drafting；law-platform-api 继续作为业务、权限、任务和版本管理中枢；law-platform-web 负责发起任务、补充缺失要素、审核和下载。": "确定技术结论：LangGraph 图、Agent 节点、模板编译器和法律研究能力保留在 law-rag-kb 代码域；legal-drafting-worker 作为独立于 FastAPI Web 进程的 Worker 领取任务并执行图；document-renderer 作为独立容器完成 LibreOffice PDF 转换和视觉检查；law-platform-api 是业务状态唯一权威，law-platform-web 提供完整人工闭环。",
            "生产环境建议使用 PostgreSQL checkpointer，单独使用 `agent_runtime` schema。`thread_id` 与 `legal_document_generation_run.id` 一一对应。MVP 可由 Python Worker 轮询 PostgreSQL 待执行任务，不强制引入 Redis；当任务并发和实时性提高后再接入队列。": "使用 PostgreSQL checkpointer，并将运行表隔离在 `agent_runtime` schema。`thread_id` 与 `legal_document_generation_run.id` 一一对应。独立 Worker 不直接轮询或写入 OA 业务表，而是通过 NestJS 内部接口领取任务、刷新租约、读取授权快照并以单调事件序号回调；后续并发量提高时可在该接口之后接入消息队列。",
            "短期可使用“文本锚点 + 表格结构指纹 + OOXML 路径”定位。生产稳定后，建议在 normalized 副本中植入 bookmark 或 Word content control，原始模板永久保留不修改。动态当事人、证据和质证条目通过复制模板行生成。": "原始模板永久只读。编译器在 normalized 副本中植入 `ld.field:<field_id>`、`ld.section:<section_id>` 和 `ld.repeat:<repeat_group>` 语义标记，并保存表格结构与样式指纹。动态证据和质证条目通过受控重复区块生成；首期多人当事人不自动复制复杂区块。",
            "以下按一个核心后端开发、一个前端/全栈开发、一个法律业务负责人和兼职测试资源估算。具体周期可根据人员并行度调整。": "本计划不承诺固定日历周期。M0—M6 均以质量门为进入下一阶段的唯一条件；人员可并行，但不得以工期替代模板、法律、安全或视觉验收。",
            "十九、需要项目负责人先拍板的决策点": "十九、已冻结的方案决策",
            "二十、建议立即执行的工作清单": "二十、分阶段执行清单",
            "20.1 第 1 周": "20.1 M0：V2.0 基线与模板技术验证",
            "20.2 第 2 周": "20.2 M1：任务、Worker 与 Checkpoint",
            "20.3 第一阶段完成定义": "20.3 M2—M6：按质量门推进",
            "第二阶段选择一份包含己方证据目录和对方证据质证表的答辩状，优先考虑知识产权类模板，以验证多表格、重复行、证据逐条质证和复杂案由扩展字段。": "第二模板固定为“要素式侵害商标权纠纷答辩状”，用于验证答辩事项、己方证据目录、对方证据逐项质证、重复证据行、知识产权扩展字段和跨模板公共字段复用。",
            "完成上述 12 个决策点的书面确认。": "登记 V2.0 已冻结决策、接口、状态、错误码和验收口径。",
            "在 law-rag-kb 创建 workflows/legal_drafting 和 template_engine 目录骨架。": "完成首个模板 sidecar schema、normalized 副本、字段绑定和空白渲染基线。",
            "安装 LangGraph 及 PostgreSQL checkpointer 依赖，建立 agent_runtime schema。": "登记 113 份模板 hash、格式、表格数和结构统计；对 2 份旧 DOC 建立受控转换任务。",
            "建立模板主表、模板版本表和生成任务表的 Prisma 设计草案。": "冻结 Alembic 迁移、Worker 内部接口、generation run 状态机和事件幂等规则。",
            "将 113 份模板复制到 originals，计算 hash；转换两份旧 DOC。": "原始模板目录作为只读 originals 基线，不覆盖、不就地写入。",
            "选择并固定“民间借贷纠纷起诉状”作为 MVP 模板。": "首个模板固定为“要素式民间借贷纠纷起诉状”；第二模板固定为“要素式侵害商标权纠纷答辩状”。",
            "实现模板 compiler V0.1：段落、表格、合并单元格、占位符和结构指纹提取。": "实现任务领取、租约、心跳、取消、单调事件回调和 PostgreSQL checkpoint。",
            "人工标注首个模板的字段 schema 和 render_binding。": "Worker 异常退出后由另一 Worker 使用同一 thread_id 恢复，重复领取和回调保持幂等。",
            "实现 LangGraph 的 state、graph 和 load_case/match_template 空节点。": "建立材料解析、要素抽取、缺失中断、法律检索、五类审校、定向重写和 DOCX 回填节点。",
            "打通 NestJS 创建任务、FastAPI 启动任务和状态查询。": "打通 law-platform-web → law-platform-api → Worker → renderer → 版本归档的纵向闭环。",
            "准备 5 个脱敏民间借贷测试案件及律师金标准。": "法律负责人同步准备 20 个脱敏案件及律师确认的金标准。",
            "建立第一版节点日志、错误码和 checkpoint 恢复测试。": "完成安全、故障、模板视觉回归和法律业务验收后再进入内部试运行。",
        },
    )

    # 封面元信息与文档控制。
    cover = document.tables[0]
    set_cell(cover.cell(3, 1), "V2.0")
    set_cell(cover.cell(5, 1), "实施基线（受控内部试运行）")
    control = document.tables[1]
    for cell, value in zip(
        control.rows[1].cells,
        ["V2.0", "2026-07-22", "实施基线", "冻结 Worker、Checkpoint、模板治理、五类审校、独立渲染与质量门方案"],
        strict=True,
    ):
        set_cell(cell, value)

    # 关键架构表。
    table = document.tables[3]
    set_cell(table.cell(3, 1), "law-rag-kb + legal-drafting-worker + document-renderer")
    set_cell(table.cell(3, 2), "材料理解、RAG、LangGraph、要素抽取、五类审校、DOCX 回填、PDF 渲染与布局报告")
    set_cell(table.cell(3, 3), "不写 OA 业务表，不获得通用 OA 查询权限，不独立决定正式版本")

    set_cell(
        document.tables[7].cell(0, 0),
        "law-platform-web\n"
        "      │ ① 创建任务 / 人工补充 / 审核\n"
        "      ▼\n"
        "law-platform-api（业务状态唯一权威）\n"
        "      │ ② 固化授权快照、签发 run token、提供 Worker 内部接口\n"
        "      ▼\n"
        "legal-drafting-worker（独立进程，LangGraph + PostgreSQL checkpoint）\n"
        "      ├────────► law-rag-kb 检索、模型与材料能力\n"
        "      ├────────► Milvus / Qwen3.7-plus / Qwen3-vl-plus\n"
        "      └────────► document-renderer（LibreOffice + 中文字体）\n"
        "      │ ③ 单调事件回调、DOCX/PDF/JSON/来源/审校产物\n"
        "      ▼\n"
        "law-platform-api 归档版本 → law-platform-web 律师审核与下载",
    )

    # 修正模板审计统计。
    set_cell(document.tables[18].cell(4, 1), "2 份银行信用卡纠纷模板")
    set_cell(document.tables[18].cell(5, 1), "单份 1—7 个；70 份仅 1 个表格")

    replace_table(
        document.tables[29],
        [
            ["方法", "路径", "说明"],
            ["POST", "/internal/legal-drafting/claims", "领取下一任务并取得 run token"],
            ["POST", "/internal/legal-drafting/runs/:id/heartbeat", "刷新租约与心跳"],
            ["GET", "/internal/legal-drafting/runs/:id/case-snapshot", "取得本次授权案件快照"],
            ["GET", "/internal/legal-drafting/runs/:id/materials/:materialId/content", "下载授权材料原件"],
            ["POST", "/internal/legal-drafting/runs/:id/events", "幂等上报节点、等待、完成或失败事件"],
            ["POST", "/internal/legal-drafting/runs/:id/artifacts", "回传 DOCX/PDF 和结构化归档元数据"],
        ],
    )

    replace_table(
        document.tables[39],
        [
            ["里程碑", "推进方式", "主要工作", "质量门交付物"],
            ["M0 V2.0 基线与模板技术验证", "质量门", "模板审计、首模板 schema、normalized 样板、设计冻结", "V2.0 DOCX、资产清单、空白渲染基线"],
            ["M1 任务、Worker 与 Checkpoint", "质量门", "迁移、状态机、租约、心跳、取消、恢复、独立连接", "可暂停恢复且重复回调不重复建版本"],
            ["M2 核心案件要素闭环", "质量门", "授权快照、解析缓存、抽取、冲突、确定性计算、人工补充", "关键字段来源可定位，冲突不由模型裁决"],
            ["M3 法律研究与分块撰写", "质量门", "过滤检索、依据卡片、写作计划、分块草稿", "关键事实 100% 有来源，法条 100% 可核验"],
            ["M4 五类审校与版本管理", "质量门", "五类审校、定向重写、来源侧栏、版本差异、审核", "严重问题阻断，自动与人工版本完整追溯"],
            ["M5 渲染与内部试运行", "质量门", "独立渲染器、字体报告、视觉回归、20 个金标准案件", "无占位符、截断、异常空白页或破坏性错位"],
            ["M6 第二模板扩展", "质量门", "商标侵权答辩状、证据目录、逐项质证、重复行", "第二模板验收后再按高频扩展，不批量激活 113 份"],
            ["后续扩展", "持续质量门", "按高频和模板家族逐份治理、验证、激活", "不设一次性全量激活目标；每个模板独立回归"],
        ],
    )

    decisions = document.tables[45]
    for row in decisions.rows[1:]:
        set_cell(row.cells[3], "已确认")
    set_cell(decisions.cell(2, 2), "LangGraph 代码在 law-rag-kb，使用独立 legal-drafting-worker 执行；renderer 独立容器")
    set_cell(decisions.cell(10, 2), "NestJS generation run + 内部领取接口 + Worker 租约/心跳 + PostgreSQL checkpoint")

    set_cell(
        document.tables[49].cell(0, 0),
        "最终结论\n"
        "采用“law-platform-api 业务权威 + 独立 legal-drafting-worker + law-rag-kb AI 能力 + 独立 document-renderer”的受控架构。"
        "首个 active 模板为要素式民间借贷纠纷起诉状，首期只覆盖核心字段闭环；第二模板为要素式侵害商标权纠纷答辩状。"
        "原件永久只读，normalized 副本植入语义标记。所有产物均标记为 AI 草稿，必须经固定开发律师身份审核；M0—M6 不设固定截止日期，只按质量门推进。",
    )
    set_cell(
        document.tables[49].cell(0, 1),
        "落地结构\n"
        "LangGraph 图、模板编译器与法律研究服务位于 law-rag-kb；独立 legal-drafting-worker 通过 NestJS 内部接口领取任务并使用 agent_runtime checkpoint；独立 document-renderer 输出 PDF、页面图与字体/占位符报告。law-platform-api 保存案件授权快照、业务状态、来源、审校和版本，law-platform-web 完成人工补充、来源审阅、律师通过/退回与下载。",
    )

    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    document.save(destination)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: build_legal_drafting_plan_v2.py SOURCE.docx OUTPUT.docx")
    main(sys.argv[1], sys.argv[2])
