"""知识库文档和案件的统一授权策略。未知权限级别默认拒绝。"""
from collections.abc import Iterable
import logging

from sqlalchemy import or_, select

from app.core.database import SessionLocal
from app.core.security import Principal
from app.models.tables import case_assignment, case_main, kb_document

logger = logging.getLogger("uvicorn.error")

_PUBLIC = "public"
_INTERNAL = "internal"
_DEPARTMENT = "department"
_PRIVATE = "private"
_CASE = "case"


def authorized_doc_ids(
    principal: Principal,
    requested_doc_ids: list[int] | None = None,
    *,
    case_id_scope: int | None = None,
    success_only: bool = True,
) -> list[int] | None:
    """返回允许的 doc_id；服务身份的 None 表示不附加过滤。

    用户身份永远返回显式列表（包括空列表），避免空授权范围被解释为全库。
    """
    normalized = _normalize_ids(requested_doc_ids)
    with SessionLocal() as db:
        query = select(
            kb_document.c.id,
            kb_document.c.permission_level,
            kb_document.c.source_department_id,
            kb_document.c.author_employee_id,
            kb_document.c.created_by,
            kb_document.c.case_id,
            kb_document.c.source_type,
        ).where(
            kb_document.c.deleted_at.is_(None),
            kb_document.c.status == "active",
        )
        if success_only:
            query = query.where(kb_document.c.embedding_status == "success")
        if normalized is not None:
            if not normalized:
                return []
            query = query.where(kb_document.c.id.in_(normalized))
        documents = db.execute(query).mappings().all()
        if principal.is_service:
            return [int(row["id"]) for row in documents]
        case_ids = _accessible_case_ids(db, principal)

    allowed = [
        int(row["id"])
        for row in documents
        if _can_access_row(principal, row, case_ids, case_id_scope)
    ]
    denied_count = len(documents) - len(allowed)
    if denied_count:
        logger.info(
            "rag_access filtered user_id=%s requested=%s allowed=%s denied=%s",
            principal.user_id,
            len(documents),
            len(allowed),
            denied_count,
        )
    return allowed


def can_access_document(principal: Principal, doc_id: int) -> bool:
    scope = authorized_doc_ids(
        principal, [doc_id], success_only=False
    )
    return scope is None or doc_id in scope


def can_access_case(principal: Principal, case_id: int) -> bool:
    if principal.is_service or principal.is_admin:
        return True
    with SessionLocal() as db:
        return case_id in _accessible_case_ids(db, principal)


def _accessible_case_ids(db, principal: Principal) -> set[int]:
    if principal.is_admin:
        rows = db.execute(
            select(case_main.c.id).where(
                case_main.c.deleted_at.is_(None), case_main.c.status == "active"
            )
        ).scalars()
        return {int(value) for value in rows}
    if principal.employee_id is None:
        return set()
    assigned = db.execute(
        select(case_assignment.c.case_id).where(
            case_assignment.c.employee_id == principal.employee_id,
            case_assignment.c.deleted_at.is_(None),
            case_assignment.c.status == "active",
        )
    ).scalars()
    managed = db.execute(
        select(case_main.c.id).where(
            case_main.c.deleted_at.is_(None),
            case_main.c.status == "active",
            or_(
                case_main.c.main_lawyer_id == principal.employee_id,
                case_main.c.case_manager_id == principal.employee_id,
            ),
        )
    ).scalars()
    return {int(value) for value in (*assigned, *managed)}


def _can_access_row(
    principal: Principal,
    row,
    accessible_case_ids: set[int],
    case_id_scope: int | None,
) -> bool:
    doc_case_id = int(row["case_id"]) if row["case_id"] is not None else None
    source_type = str(row["source_type"] or "")
    owner = (
        row["author_employee_id"] is not None
        and principal.employee_id == int(row["author_employee_id"])
    ) or (
        row["created_by"] is not None
        and principal.user_id == int(row["created_by"])
    )

    # 案件上下文不能跨案召回；全局法规仍可作为案件问答依据。
    if case_id_scope is not None:
        if doc_case_id not in {None, case_id_scope}:
            return False
        if doc_case_id is None and source_type == "case_material":
            return False

    # 管理员可绕过文档权限级别，但案件问答的显式 case scope 仍是硬边界，
    # 避免一次案件会话把另一案件的材料送入模型上下文。
    if principal.is_admin:
        return True

    # 只要绑定案件，就必须是案件成员；public 不能绕过案件隔离。
    if doc_case_id is not None and doc_case_id not in accessible_case_ids:
        return False

    # 未绑定案件的案件材料按私有文档处理，避免脏数据扩大可见范围。
    if source_type == "case_material" and doc_case_id is None:
        return owner

    level = str(row["permission_level"] or "").strip().lower()
    if level == _PUBLIC:
        return True
    if level == _INTERNAL:
        return principal.employee_id is not None
    if level == _DEPARTMENT:
        return (
            row["source_department_id"] is not None
            and principal.department_id == int(row["source_department_id"])
        )
    if level == _PRIVATE:
        return owner
    if level == _CASE:
        return doc_case_id is not None and doc_case_id in accessible_case_ids
    return False


def _normalize_ids(values: Iterable[int] | None) -> list[int] | None:
    if values is None:
        return None
    return sorted({int(value) for value in values if int(value) > 0})
