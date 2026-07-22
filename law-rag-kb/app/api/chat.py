"""问答 API：POST /chat（RAG 检索→生成→引用，结果写 ai_chat_log）。"""
import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, PositiveInt

from app.core.authorization import authorized_doc_ids, can_access_case
from app.core.config import settings
from app.core.security import Principal, require_user_principal
from app.rag import chat as chat_service
from app.rag.llm import LLMServiceError

router = APIRouter(tags=["chat"])
logger = logging.getLogger("uvicorn.error")


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000, description="用户问题")
    session_id: str | None = Field(
        None, min_length=1, max_length=100, description="会话 id；不传则自动生成 uuid"
    )
    user_id: PositiveInt | None = Field(
        None, description="仅用于未启用认证的兼容模式；生产身份取自可信请求头"
    )
    user_type: str = Field("user", max_length=50)
    case_id: PositiveInt | None = None
    top_k: int | None = Field(None, ge=1, le=20, description="送 LLM 的片段数，默认 CHAT_TOP_K")
    doc_ids: list[PositiveInt] | None = Field(
        None, max_length=200, description="限定检索范围；最终范围由服务端授权收窄"
    )


class ChatRefModel(BaseModel):
    ref_id: int
    chunk_id: str
    doc_id: int
    doc_title: str | None
    chunk_idx: int
    source: str
    score: float
    article_no: str | None = None
    chapter: str | None = None
    content_type: str = "text"
    image_id: int | None = None
    page_no: int | None = None
    image_category: str | None = None
    category_id: int | None = None
    category_path: list[str] | None = None
    text: str = ""


class ChatResponse(BaseModel):
    question: str
    answer: str
    refs: list[ChatRefModel]
    chat_log_id: int | None
    hits_count: int


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    principal: Annotated[Principal, Depends(require_user_principal)],
) -> ChatResponse:
    """RAG 问答：检索 → 生成 → 引用，结果写 ai_chat_log。

    def（非 async def）：retrieve/rerank/LLM（stub 为 CPU-bound，真实 LLM 为阻塞 IO），
    由 threadpool 执行不阻塞事件循环。
    """
    session_id = req.session_id or uuid.uuid4().hex
    if settings.auth_enabled and req.user_id not in {None, principal.user_id}:
        raise HTTPException(status_code=403, detail="user context mismatch")
    if req.case_id is not None and not can_access_case(principal, req.case_id):
        # 不泄露案件是否存在。
        logger.info(
            "rag_chat_access decision=deny user_id=%s case_id=%s reason=case_scope",
            principal.user_id,
            req.case_id,
        )
        raise HTTPException(status_code=404, detail="case not found")

    doc_scope = authorized_doc_ids(
        principal,
        req.doc_ids,
        case_id_scope=req.case_id,
    )
    logger.info(
        "rag_chat_access decision=allow user_id=%s case_id=%s allowed_docs=%s",
        principal.user_id,
        req.case_id,
        len(doc_scope) if doc_scope is not None else "all",
    )
    effective_user_id = principal.user_id if settings.auth_enabled else req.user_id
    effective_user_type = "user" if settings.auth_enabled else req.user_type
    try:
        result = chat_service.chat(
            req.question,
            session_id=session_id,
            user_id=effective_user_id,
            user_type=effective_user_type,
            case_id=req.case_id,
            top_k=req.top_k,
            doc_ids=doc_scope,
        )
    except LLMServiceError as e:
        # 只返回已脱敏的稳定错误，不把供应商响应、请求头或 API Key 暴露给调用方。
        raise HTTPException(status_code=502, detail=str(e)) from e
    return ChatResponse(
        question=req.question,
        answer=result.answer,
        refs=[ChatRefModel(**r) for r in result.refs],
        chat_log_id=result.chat_log_id,
        hits_count=result.hits_count,
    )
