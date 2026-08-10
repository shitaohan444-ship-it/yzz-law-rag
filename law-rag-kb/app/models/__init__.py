"""知识库相关表的 SQLAlchemy Core 声明。

law-rag-service 是这些表的 schema owner（由 Alembic 迁移管理 DDL）；
本服务只读/回写业务字段，不修改列定义，故用 Core Table 只声明实际触碰的列，
不重新声明 ORM 类（避免与 law-rag-service 的生成模型 drift）。
"""
