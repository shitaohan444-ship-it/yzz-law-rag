"""RAG 问答编排：检索 → prompt → LLM 生成 → 引用标注 → 写 ai_chat_log。

纯函数编排（与 retrieve 一致），不引入 LangGraph（留作后续多轮/Agent 增强再上状态机）。
session_id/user_id/user_type/case_id 等业务字段由 API 层传入；HTTP API 已完成服务认证、
数据库身份校验与文档范围授权。直接调用本模块的内部代码必须先完成同等授权。
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import insert

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.tables import ai_chat_log
from app.rag import llm, prompt, retrieve


@dataclass
class ChatResult:
    answer: str
    refs: list[dict]
    chat_log_id: int | None
    hits_count: int


# 无强相关依据时的固定拒答文案（含"无法回答"，对齐 run_stage_tests C8 断言）
_REFUSE_ANSWER = (
    "知识库中暂无与该问题直接相关的法律依据，无法回答该问题。"
    "建议补充相关法律法规后重试，或咨询专业律师。"
)


def chat(
    question: str,
    *,
    session_id: str,
    user_id: int | None = None,
    user_type: str = "user",
    case_id: int | None = None,
    top_k: int | None = None,
    doc_ids: list[int] | None = None,
) -> ChatResult:
    """RAG 问答编排：检索 → 生成 → 引用 → 落库 ai_chat_log。"""
    k = top_k if top_k is not None else settings.chat_top_k
    hits = retrieve.search(question, doc_ids=doc_ids, top_k=k)

    # 无强相关依据 → 代码层硬拒答（不调 LLM，避免幻觉，行为稳定）：
    # retrieve 已按 rerank_min_score 过滤，仅当无任何片段达标（只剩保底 top-1）时
    # hits[0].score < rerank_min_score，表明库内无相关法律依据。
    top_score = hits[0].score if hits else 0.0
    if top_score < settings.rerank_min_score:
        answer = _REFUSE_ANSWER
        refs = []
        chat_log_id = _log_chat(
            session_id=session_id,
            user_id=user_id,
            user_type=user_type,
            case_id=case_id,
            question=question,
            answer=answer,
            refs=refs,
        )
        return ChatResult(
            answer=answer, refs=refs, chat_log_id=chat_log_id, hits_count=0
        )

    prompt_text, used = prompt.build_prompt(
        question, hits, max_chars=settings.chat_max_context_chars
    )
    stable_refs = prompt.build_refs(used)

    answer = llm.get_llm().generate(prompt_text)

    chat_log_id = _log_chat(
        session_id=session_id,
        user_id=user_id,
        user_type=user_type,
        case_id=case_id,
        question=question,
        answer=answer,
        refs=stable_refs,
    )
    # 日志保存稳定 #img:id；API 返回副本才解析为有时效的预签名 URL。
    from app.ingest import service as ingest_service

    resolved_texts = ingest_service.resolve_markdown_texts(
        [str(ref.get("text") or "") for ref in stable_refs]
    )
    refs = [dict(ref, text=resolved_texts[i]) for i, ref in enumerate(stable_refs)]
    return ChatResult(
        answer=answer,
        refs=refs,
        chat_log_id=chat_log_id,
        hits_count=len(used),
    )


def _log_chat(
    *,
    session_id: str,
    user_id: int | None,
    user_type: str,
    case_id: int | None,
    question: str,
    answer: str,
    refs: list[dict],
) -> int:
    """写一条 ai_chat_log，返回日志 id。独立短事务，不与检索/生成耦合。"""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        result = db.execute(
            insert(ai_chat_log)
            .values(
                session_id=session_id,
                user_type=user_type,
                user_id=user_id,
                case_id=case_id,
                question_text=question,
                answer_text=answer,
                knowledge_refs=refs if refs else None,
                manual_takeover_flag=False,
                risk_flag=False,
                created_at=now,
                updated_at=now,
                status="active",
            )
            .returning(ai_chat_log.c.id)
        )
        db.commit()
        return result.scalar()
