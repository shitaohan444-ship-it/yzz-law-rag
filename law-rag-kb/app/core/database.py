"""PG 连接（复用 law-rag-service 模式 + search_path=oa 技巧）。

只读为主（kb_document 等）；里程碑 1 仅用于 /health 的 SELECT 1。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url_with_search_path, future=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()


def get_db():
    """FastAPI 依赖：yield 一个 Session，请求结束关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
