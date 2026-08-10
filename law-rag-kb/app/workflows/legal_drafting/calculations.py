from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def as_money(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("元", "").strip())
    except (InvalidOperation, ValueError):
        return None


def calculate_claim_total(values: dict) -> str | None:
    parts = [
        as_money(values.get("claims.principal.amount")),
        as_money(values.get("claims.interest.amount")),
        as_money(values.get("claims.enforcement_costs")),
    ]
    known = [part for part in parts if part is not None]
    if not known:
        return None
    total = sum(known, Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{total:.2f} 元"


def overdue_days(start: str | None, end: date | None = None) -> int | None:
    if not start:
        return None
    try:
        started = date.fromisoformat(start)
    except ValueError:
        return None
    return max(0, ((end or date.today()) - started).days)


def calculate_simple_interest(
    principal,
    annual_rate_percent,
    start: str | None,
    end: str | None,
) -> str | None:
    """按实际天数/365 计算单利；任一输入不明确时拒绝推算。"""
    principal_value = as_money(principal)
    rate_value = as_money(annual_rate_percent)
    if principal_value is None or rate_value is None or not start or not end:
        return None
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError:
        return None
    days = (end_date - start_date).days
    if days < 0 or rate_value < 0:
        return None
    interest = (
        principal_value * rate_value / Decimal("100") * Decimal(days) / Decimal("365")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{interest:.2f} 元"
