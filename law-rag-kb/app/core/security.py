"""RAG 服务间认证和经过数据库校验的调用者身份。

生产拓扑要求 Node/API Gateway 持有服务 Token；终端用户不能直接访问 RAG。
Gateway 在通过自身登录态后附加 X-RAG-User-Id，RAG 再从 oa.sys_user/sys_employee
加载真实身份。用户 ID 只有在 Bearer Token 已验证后才会被接受。
"""
from dataclasses import dataclass
from datetime import date
import logging
import secrets
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException
from sqlalchemy import and_, or_, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.tables import sys_employee, sys_role, sys_user, sys_user_role

logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class Principal:
    user_id: int | None
    employee_id: int | None
    department_id: int | None
    role_codes: frozenset[str] = frozenset()
    data_scopes: frozenset[str] = frozenset()
    is_service: bool = False
    is_admin: bool = False


_SERVICE_PRINCIPAL = Principal(
    user_id=None,
    employee_id=None,
    department_id=None,
    is_service=True,
    is_admin=True,
)


def require_service_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """验证内部服务 Bearer Token；开发模式保持现有脚本兼容。"""
    if not settings.auth_enabled:
        if settings.is_production:
            raise HTTPException(status_code=503, detail="RAG authentication is not configured")
        return _SERVICE_PRINCIPAL

    if settings.auth_configuration_status != "ok":
        logger.error("rag_auth misconfigured")
        raise HTTPException(status_code=503, detail="RAG authentication is not configured")

    scheme, _, supplied = (authorization or "").partition(" ")
    valid = scheme.lower() == "bearer" and secrets.compare_digest(
        supplied, settings.rag_service_token
    )
    if not valid:
        logger.warning("rag_auth denied reason=invalid_service_credentials")
        raise HTTPException(
            status_code=401,
            detail="invalid service credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _SERVICE_PRINCIPAL


def require_user_principal(
    service: Annotated[Principal, Depends(require_service_principal)],
    user_id: Annotated[int | None, Header(alias="X-RAG-User-Id")] = None,
) -> Principal:
    """服务认证后解析活动用户；认证启用时不允许匿名读取。"""
    if not settings.auth_enabled:
        return service
    if user_id is None or user_id <= 0:
        logger.warning("rag_auth denied reason=missing_user_context")
        raise HTTPException(status_code=401, detail="authenticated user context required")

    principal = load_user_principal(user_id)
    if principal is None:
        logger.warning("rag_auth denied reason=inactive_user user_id=%s", user_id)
        raise HTTPException(status_code=401, detail="invalid or inactive user")
    return principal


def load_user_principal(user_id: int) -> Principal | None:
    """只信任数据库活动账号、活动员工和当前有效角色。"""
    today = date.today()
    with SessionLocal() as db:
        row = db.execute(
            select(
                sys_user.c.id,
                sys_user.c.employee_id,
                sys_employee.c.department_id,
            )
            .select_from(
                sys_user.join(
                    sys_employee, sys_employee.c.id == sys_user.c.employee_id
                )
            )
            .where(
                sys_user.c.id == user_id,
                sys_user.c.account_status == "active",
                sys_user.c.status == "active",
                sys_user.c.deleted_at.is_(None),
                sys_employee.c.employment_status == "active",
                sys_employee.c.status == "active",
                sys_employee.c.deleted_at.is_(None),
            )
        ).mappings().first()
        if row is None:
            return None

        roles = db.execute(
            select(
                sys_role.c.role_code,
                sys_role.c.data_scope,
                sys_role.c.permission_json,
            )
            .select_from(
                sys_user_role.join(
                    sys_role, sys_role.c.id == sys_user_role.c.role_id
                )
            )
            .where(
                or_(
                    sys_user_role.c.user_id == user_id,
                    and_(
                        sys_user_role.c.user_id.is_(None),
                        sys_user_role.c.employee_id == row["employee_id"],
                    ),
                ),
                sys_user_role.c.status == "active",
                sys_user_role.c.deleted_at.is_(None),
                or_(
                    sys_user_role.c.effective_date.is_(None),
                    sys_user_role.c.effective_date <= today,
                ),
                or_(
                    sys_user_role.c.expire_date.is_(None),
                    sys_user_role.c.expire_date >= today,
                ),
                sys_role.c.status == "active",
                sys_role.c.deleted_at.is_(None),
            )
        ).mappings().all()

    role_codes = frozenset(
        str(item["role_code"]).strip().lower()
        for item in roles
        if item["role_code"] is not None
    )
    data_scopes = frozenset(
        str(item["data_scope"]).strip().lower()
        for item in roles
        if item["data_scope"] is not None
    )
    explicit_admin = any(
        "rag.admin" in _flatten_permissions(item["permission_json"]) for item in roles
    )
    is_admin = bool(
        role_codes.intersection(settings.admin_role_codes)
        or "all" in data_scopes
        or explicit_admin
    )
    return Principal(
        user_id=int(row["id"]),
        employee_id=int(row["employee_id"]),
        department_id=(
            int(row["department_id"]) if row["department_id"] is not None else None
        ),
        role_codes=role_codes,
        data_scopes=data_scopes,
        is_admin=is_admin,
    )


def _flatten_permissions(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, str):
        result.add(value.strip().lower())
    elif isinstance(value, dict):
        for key, item in value.items():
            # {"rag.admin": false} 不能仅因键名存在而提权。
            if isinstance(item, bool):
                if item:
                    result.add(str(key).strip().lower())
            else:
                result.update(_flatten_permissions(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            result.update(_flatten_permissions(item))
    return result
