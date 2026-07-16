"""FastAPI 入口。

阶段 1：服务骨架 + 连通 PG/MinIO/Milvus + /health。
阶段 2：挂 /documents 入库链路由。
阶段 3：挂 /search 检索链路由（hybrid 召回 + bge-reranker 精排）。
阶段 4：挂 /chat 生成链路由（检索→LLM 生成→引用，写 ai_chat_log）。
"""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.search import router as search_router
from app.core.config import settings
from app.core.database import engine

logger = logging.getLogger("uvicorn.error")


class _PayloadTooLarge(Exception):
    pass


class MaxBodySizeMiddleware:
    """同时限制 Content-Length 和分块传输，避免绕过请求体上限。"""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    await JSONResponse(
                        status_code=413, content={"detail": "request body too large"}
                    )(scope, receive, send)
                    return
            except ValueError:
                await JSONResponse(
                    status_code=400, content={"detail": "invalid content-length"}
                )(scope, receive, send)
                return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _PayloadTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _PayloadTooLarge:
            await JSONResponse(
                status_code=413, content={"detail": "request body too large"}
            )(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.is_production and settings.auth_configuration_status != "ok":
        logger.critical("refusing startup: production RAG authentication is misconfigured")
        raise RuntimeError("production RAG authentication is not configured")
    # MilvusClient 懒连接，无需显式 connect；PG/MinIO 按需连，无独占池
    yield
    # 关闭：释放 PG engine（MilvusClient grpc 通道随进程退出）
    engine.dispose()


_docs_enabled = settings.expose_api_docs and not settings.is_production
app = FastAPI(
    title="law-rag-kb",
    description="知识库 RAG 服务（Python / FastAPI）",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

if settings.allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

app.add_middleware(MaxBodySizeMiddleware, max_bytes=settings.max_request_body_bytes)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-RAG-User-Id"],
    )


@app.middleware("http")
async def production_safety_headers(request: Request, call_next):
    """为所有应用响应附加基础安全头。"""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if settings.is_production:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response

app.include_router(health_router)
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(chat_router)
