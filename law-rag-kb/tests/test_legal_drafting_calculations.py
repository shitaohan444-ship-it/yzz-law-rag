from datetime import date

from app.workflows.legal_drafting.calculations import (
    calculate_claim_total,
    calculate_simple_interest,
    overdue_days,
)


def test_claim_total_uses_only_explicit_amounts():
    assert calculate_claim_total(
        {
            "claims.principal.amount": "100,000元",
            "claims.interest.amount": "1000.50",
            "claims.enforcement_costs": None,
        }
    ) == "101000.50 元"


def test_interest_and_overdue_dates_are_deterministic():
    assert calculate_simple_interest("100000", "12", "2025-01-01", "2025-01-31") == "986.30 元"
    assert overdue_days("2025-01-01", date(2025, 1, 31)) == 30
    assert calculate_simple_interest("100000", "12", "2025-02-01", "2025-01-01") is None
