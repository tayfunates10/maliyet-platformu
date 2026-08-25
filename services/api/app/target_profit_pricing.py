"""Deterministic Decimal-only target-profit pricing primitives.

The module computes the unit price and total revenue required to recover an
explicit variable cost per unit, explicit fixed costs, and an explicit target
profit over an explicit expected sales quantity. It never infers tax, inflation,
financing, demand, or a currency-rounding policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)

ENGINE_VERSION = "target-profit-pricing-v2"
DECIMAL_PRECISION = 128
MAX_INPUT_SIGNIFICANT_DIGITS = 38
MAX_INPUT_SCALE = 18
MAX_INPUT_INTEGER_DIGITS = 38
ZERO = Decimal("0")
ENGINE_CONTEXT = Context(
    prec=DECIMAL_PRECISION,
    rounding=ROUND_HALF_EVEN,
    Emin=-999_999,
    Emax=999_999,
    capitals=1,
    clamp=0,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)


class TargetProfitPricingInputError(ValueError):
    """Raised when target-profit pricing inputs violate the public contract."""


def _require_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TargetProfitPricingInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise TargetProfitPricingInputError(f"{field} must be finite")

    decimal_tuple = value.as_tuple()
    exponent = decimal_tuple.exponent
    if not isinstance(exponent, int):
        raise TargetProfitPricingInputError(f"{field} must be finite")
    significant_digits = len(decimal_tuple.digits)
    scale = max(-exponent, 0)
    integer_digits = max(value.copy_abs().adjusted() + 1, 0) if value != ZERO else 0
    if significant_digits > MAX_INPUT_SIGNIFICANT_DIGITS:
        raise TargetProfitPricingInputError(
            f"{field} exceeds {MAX_INPUT_SIGNIFICANT_DIGITS} significant digits"
        )
    if scale > MAX_INPUT_SCALE:
        raise TargetProfitPricingInputError(f"{field} exceeds scale {MAX_INPUT_SCALE}")
    if integer_digits > MAX_INPUT_INTEGER_DIGITS:
        raise TargetProfitPricingInputError(
            f"{field} exceeds {MAX_INPUT_INTEGER_DIGITS} integer digits"
        )
    return value


def _require_non_negative(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value < ZERO:
        raise TargetProfitPricingInputError(f"{field} must be non-negative")
    return decimal_value


@dataclass(frozen=True)
class TargetProfitPricingResult:
    """Exact target-profit pricing result before any currency rounding policy."""

    variable_cost_per_unit: Decimal
    fixed_costs: Decimal
    target_profit: Decimal
    expected_units: Decimal
    required_contribution_total: Decimal
    required_contribution_per_unit: Decimal
    required_price_per_unit: Decimal
    required_revenue: Decimal


def calculate_target_profit_price(
    *,
    variable_cost_per_unit: Decimal,
    fixed_costs: Decimal,
    target_profit: Decimal,
    expected_units: Decimal,
) -> TargetProfitPricingResult:
    """Calculate price required to reach an explicit target profit.

    Formula::

        contribution_total = fixed_costs + target_profit
        contribution_per_unit = contribution_total / expected_units
        required_revenue = variable_cost_per_unit * expected_units + contribution_total
        required_price_per_unit = required_revenue / expected_units

    Arithmetic runs under a fully engine-owned Decimal context. Its precision is
    deliberately wider than the supported 38-digit operands so a 76-digit
    product can still retain the maximum supported fractional residual. No
    implicit currency rounding is applied.
    """

    variable = _require_non_negative(
        variable_cost_per_unit,
        field="variable_cost_per_unit",
    )
    fixed = _require_non_negative(fixed_costs, field="fixed_costs")
    target = _require_non_negative(target_profit, field="target_profit")
    units = _require_decimal(expected_units, field="expected_units")
    if units <= ZERO:
        raise TargetProfitPricingInputError("expected_units must be greater than 0")

    with localcontext(ENGINE_CONTEXT):
        contribution_total = fixed + target
        contribution_per_unit = contribution_total / units
        required_revenue = variable * units + contribution_total
        required_price = required_revenue / units

    return TargetProfitPricingResult(
        variable_cost_per_unit=variable,
        fixed_costs=fixed,
        target_profit=target,
        expected_units=units,
        required_contribution_total=contribution_total,
        required_contribution_per_unit=contribution_per_unit,
        required_price_per_unit=required_price,
        required_revenue=required_revenue,
    )


def build_target_profit_pricing_snapshot(
    result: TargetProfitPricingResult,
) -> dict[str, object]:
    """Serialize a reproducible target-profit pricing artifact."""

    return {
        "engine_version": ENGINE_VERSION,
        "decimal_policy": {
            "precision": DECIMAL_PRECISION,
            "rounding": "ROUND_HALF_EVEN",
            "emin": ENGINE_CONTEXT.Emin,
            "emax": ENGINE_CONTEXT.Emax,
            "max_input_significant_digits": MAX_INPUT_SIGNIFICANT_DIGITS,
            "max_input_scale": MAX_INPUT_SCALE,
            "max_input_integer_digits": MAX_INPUT_INTEGER_DIGITS,
            "implicit_currency_rounding": False,
        },
        "variable_cost_per_unit": str(result.variable_cost_per_unit),
        "fixed_costs": str(result.fixed_costs),
        "target_profit": str(result.target_profit),
        "expected_units": str(result.expected_units),
        "required_contribution_total": str(result.required_contribution_total),
        "required_contribution_per_unit": str(result.required_contribution_per_unit),
        "required_price_per_unit": str(result.required_price_per_unit),
        "required_revenue": str(result.required_revenue),
        "tax_inferred": False,
    }
