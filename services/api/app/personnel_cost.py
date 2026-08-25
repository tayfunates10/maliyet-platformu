"""Deterministic Decimal-only employer personnel cost composition.

The module composes explicit gross cash compensation, an already-resolved SGK
premium result, and explicit additional employer-paid cost lines. It never
hard-codes payroll rates, infers employee income tax, or converts employee
withholdings into employer cost.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.calculation_kernel import SgkPremiumResult

ENGINE_VERSION = "personnel-cost-v1"
ZERO = Decimal("0")


class PersonnelCostInputError(ValueError):
    """Raised when employer personnel cost inputs violate the contract."""


def _require_non_negative_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise PersonnelCostInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise PersonnelCostInputError(f"{field} must be finite")
    if value < ZERO:
        raise PersonnelCostInputError(f"{field} must be non-negative")
    return value


@dataclass(frozen=True)
class EmployerCostLine:
    """One explicit employer-paid cost outside gross cash compensation and SGK."""

    key: str
    amount: Decimal

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise PersonnelCostInputError("employer_cost.key must not be blank")
        _require_non_negative_decimal(
            self.amount,
            field=f"employer_cost[{self.key}].amount",
        )


@dataclass(frozen=True)
class PersonnelCostResult:
    """Employer-side personnel cost for one calculation period."""

    gross_cash_compensation: Decimal
    employer_sgk_premium: Decimal
    additional_employer_costs: Decimal
    total_employer_cost: Decimal
    employer_cost_lines: tuple[EmployerCostLine, ...]
    sgk_limits_rule_snapshot: dict[str, object]
    sgk_rates_rule_snapshot: dict[str, object]


def calculate_personnel_cost(
    *,
    gross_cash_compensation: Decimal,
    sgk_premium: SgkPremiumResult,
    additional_employer_costs: Sequence[EmployerCostLine] = (),
) -> PersonnelCostResult:
    """Compose the real employer personnel cost without payroll-rate inference.

    `sgk_premium` must come from the rule-resolved SGK calculation boundary.
    Employee SGK deductions are intentionally excluded because they are withheld
    from employee compensation rather than added as a second employer cost.
    """

    gross = _require_non_negative_decimal(
        gross_cash_compensation,
        field="gross_cash_compensation",
    )
    employer_sgk = _require_non_negative_decimal(
        sgk_premium.employer_premium,
        field="sgk_premium.employer_premium",
    )

    seen: set[str] = set()
    ordered_lines = tuple(sorted(additional_employer_costs, key=lambda line: line.key))
    for line in ordered_lines:
        if line.key in seen:
            raise PersonnelCostInputError(f"duplicate employer cost key: {line.key}")
        seen.add(line.key)

    additional_total = sum((line.amount for line in ordered_lines), ZERO)
    total = gross + employer_sgk + additional_total

    return PersonnelCostResult(
        gross_cash_compensation=gross,
        employer_sgk_premium=employer_sgk,
        additional_employer_costs=additional_total,
        total_employer_cost=total,
        employer_cost_lines=ordered_lines,
        sgk_limits_rule_snapshot=dict(sgk_premium.limits_rule_snapshot),
        sgk_rates_rule_snapshot=dict(sgk_premium.rates_rule_snapshot),
    )


def build_personnel_cost_snapshot(result: PersonnelCostResult) -> dict[str, object]:
    """Serialize exact employer cost values and SGK provenance for persistence."""

    return {
        "engine_version": ENGINE_VERSION,
        "gross_cash_compensation": str(result.gross_cash_compensation),
        "employer_sgk_premium": str(result.employer_sgk_premium),
        "additional_employer_costs": str(result.additional_employer_costs),
        "total_employer_cost": str(result.total_employer_cost),
        "employer_cost_lines": [
            {"key": line.key, "amount": str(line.amount)} for line in result.employer_cost_lines
        ],
        "sgk_limits_rule_snapshot": result.sgk_limits_rule_snapshot,
        "sgk_rates_rule_snapshot": result.sgk_rates_rule_snapshot,
        "employee_income_tax_inferred": False,
        "employee_withholdings_added_to_employer_cost": False,
    }
