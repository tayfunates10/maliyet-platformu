"""Regression tests for deterministic employer personnel cost composition."""

from decimal import Decimal

import pytest

from app.calculation_kernel import SgkPremiumResult
from app.personnel_cost import (
    EmployerCostLine,
    PersonnelCostInputError,
    build_personnel_cost_snapshot,
    calculate_personnel_cost,
)


def _sgk_result() -> SgkPremiumResult:
    return SgkPremiumResult(
        declared_monthly_earnings=Decimal("30000.00"),
        premium_base=Decimal("30000.00"),
        minimum_premium_base=Decimal("20000.00"),
        maximum_premium_base=Decimal("150000.00"),
        employer_premium=Decimal("6750.00"),
        employee_premium=Decimal("4500.00"),
        combined_premium=Decimal("11250.00"),
        limits_rule_snapshot={"rule_key": "sgk-pek", "version": "2026-01"},
        rates_rule_snapshot={"rule_key": "sgk-rates", "version": "2026-01"},
    )


def test_personnel_cost_composes_employer_side_costs_only() -> None:
    result = calculate_personnel_cost(
        gross_cash_compensation=Decimal("30000.00"),
        sgk_premium=_sgk_result(),
        additional_employer_costs=(
            EmployerCostLine("meal-employer-share", Decimal("1500.00")),
            EmployerCostLine("private-insurance", Decimal("750.00")),
        ),
    )

    assert result.gross_cash_compensation == Decimal("30000.00")
    assert result.employer_sgk_premium == Decimal("6750.00")
    assert result.additional_employer_costs == Decimal("2250.00")
    assert result.total_employer_cost == Decimal("39000.00")
    assert result.total_employer_cost != Decimal("43500.00")


def test_employee_sgk_is_not_double_counted_as_employer_cost() -> None:
    result = calculate_personnel_cost(
        gross_cash_compensation=Decimal("30000.00"),
        sgk_premium=_sgk_result(),
    )

    assert result.total_employer_cost == Decimal("36750.00")
    assert _sgk_result().employee_premium == Decimal("4500.00")


def test_additional_cost_lines_are_deterministic_and_unique() -> None:
    result = calculate_personnel_cost(
        gross_cash_compensation=Decimal("1000.00"),
        sgk_premium=_sgk_result(),
        additional_employer_costs=(
            EmployerCostLine("z-benefit", Decimal("2.00")),
            EmployerCostLine("a-benefit", Decimal("1.00")),
        ),
    )

    assert tuple(line.key for line in result.employer_cost_lines) == (
        "a-benefit",
        "z-benefit",
    )

    with pytest.raises(PersonnelCostInputError, match="duplicate employer cost key"):
        calculate_personnel_cost(
            gross_cash_compensation=Decimal("1000.00"),
            sgk_premium=_sgk_result(),
            additional_employer_costs=(
                EmployerCostLine("same", Decimal("1.00")),
                EmployerCostLine("same", Decimal("2.00")),
            ),
        )


def test_binary_float_and_negative_costs_fail_closed() -> None:
    with pytest.raises(PersonnelCostInputError, match="must be Decimal"):
        calculate_personnel_cost(
            gross_cash_compensation=1000.0,  # type: ignore[arg-type]
            sgk_premium=_sgk_result(),
        )

    with pytest.raises(PersonnelCostInputError, match="must be non-negative"):
        EmployerCostLine("invalid", Decimal("-0.01"))


def test_snapshot_preserves_sgk_provenance_and_refuses_tax_inference() -> None:
    result = calculate_personnel_cost(
        gross_cash_compensation=Decimal("30000.00"),
        sgk_premium=_sgk_result(),
        additional_employer_costs=(EmployerCostLine("meal", Decimal("1000.00")),),
    )
    snapshot = build_personnel_cost_snapshot(result)

    assert snapshot["engine_version"] == "personnel-cost-v1"
    assert snapshot["total_employer_cost"] == "37750.00"
    assert snapshot["sgk_limits_rule_snapshot"] == {
        "rule_key": "sgk-pek",
        "version": "2026-01",
    }
    assert snapshot["sgk_rates_rule_snapshot"] == {
        "rule_key": "sgk-rates",
        "version": "2026-01",
    }
    assert snapshot["employee_income_tax_inferred"] is False
    assert snapshot["employee_withholdings_added_to_employer_cost"] is False
