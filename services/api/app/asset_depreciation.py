"""Deterministic Decimal-only accounting asset depreciation primitives.

The module implements explicit straight-line book depreciation only. It does not
infer statutory tax depreciation rates, useful lives, residual values, incentives,
or tax deductibility. Those policy inputs must be supplied by the caller or a
separate rule-resolution boundary.
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

ENGINE_VERSION = "asset-depreciation-v1"
DECIMAL_PRECISION = 76
DECIMAL_ROUNDING = ROUND_HALF_EVEN
MAX_INPUT_SIGNIFICANT_DIGITS = 38
MAX_INPUT_SCALE = 18
MAX_INPUT_INTEGER_DIGITS = 38
MAX_USEFUL_LIFE_MONTHS = 1_000_000
ZERO = Decimal("0")
ENGINE_CONTEXT = Context(
    prec=DECIMAL_PRECISION,
    rounding=DECIMAL_ROUNDING,
    Emin=-999_999,
    Emax=999_999,
    capitals=1,
    clamp=0,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)


class AssetDepreciationInputError(ValueError):
    """Raised when asset depreciation inputs violate the explicit contract."""


def _require_non_negative_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise AssetDepreciationInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise AssetDepreciationInputError(f"{field} must be finite")
    if value < ZERO:
        raise AssetDepreciationInputError(f"{field} must be non-negative")

    significant_digits = len(value.as_tuple().digits)
    scale = max(-value.as_tuple().exponent, 0)
    integer_digits = max(value.adjusted() + 1, 0) if value != ZERO else 0
    if significant_digits > MAX_INPUT_SIGNIFICANT_DIGITS:
        raise AssetDepreciationInputError(
            f"{field} exceeds {MAX_INPUT_SIGNIFICANT_DIGITS} significant digits"
        )
    if scale > MAX_INPUT_SCALE:
        raise AssetDepreciationInputError(f"{field} exceeds scale {MAX_INPUT_SCALE}")
    if integer_digits > MAX_INPUT_INTEGER_DIGITS:
        raise AssetDepreciationInputError(
            f"{field} exceeds {MAX_INPUT_INTEGER_DIGITS} integer digits"
        )
    return value


def _require_positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssetDepreciationInputError(f"{field} must be int")
    if value <= 0:
        raise AssetDepreciationInputError(f"{field} must be greater than 0")
    if value > MAX_USEFUL_LIFE_MONTHS:
        raise AssetDepreciationInputError(f"{field} must be at most {MAX_USEFUL_LIFE_MONTHS}")
    return value


def _require_non_negative_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssetDepreciationInputError(f"{field} must be int")
    if value < 0:
        raise AssetDepreciationInputError(f"{field} must be non-negative")
    return value


@dataclass(frozen=True)
class AssetDepreciationResult:
    """One point-in-time straight-line accounting depreciation result."""

    asset_key: str
    acquisition_cost: Decimal
    residual_value: Decimal
    depreciable_base: Decimal
    useful_life_months: int
    elapsed_months: int
    depreciation_for_period: Decimal
    accumulated_depreciation: Decimal
    carrying_amount: Decimal


def calculate_straight_line_depreciation(
    *,
    asset_key: str,
    acquisition_cost: Decimal,
    residual_value: Decimal,
    useful_life_months: int,
    elapsed_months: int,
) -> AssetDepreciationResult:
    """Calculate book depreciation with explicit caller-owned assumptions.

    `elapsed_months=0` represents the asset before the first depreciation period.
    Values beyond the explicit useful life are rejected instead of being silently
    capped. Accumulated depreciation is derived from the proportion of elapsed
    life; the final period is forced to the exact depreciable base so residual
    value is conserved without hidden currency rounding.
    """

    if not asset_key.strip():
        raise AssetDepreciationInputError("asset_key must not be blank")
    cost = _require_non_negative_decimal(acquisition_cost, field="acquisition_cost")
    residual = _require_non_negative_decimal(residual_value, field="residual_value")
    if residual > cost:
        raise AssetDepreciationInputError("residual_value cannot exceed acquisition_cost")
    life = _require_positive_int(useful_life_months, field="useful_life_months")
    elapsed = _require_non_negative_int(elapsed_months, field="elapsed_months")
    if elapsed > life:
        raise AssetDepreciationInputError("elapsed_months cannot exceed useful_life_months")

    with localcontext(ENGINE_CONTEXT):
        base = cost - residual
        if elapsed == 0:
            accumulated = ZERO
            previous_accumulated = ZERO
        else:
            accumulated = base if elapsed == life else base * Decimal(elapsed) / Decimal(life)
            previous_accumulated = (
                ZERO if elapsed == 1 else base * Decimal(elapsed - 1) / Decimal(life)
            )
        period_depreciation = accumulated - previous_accumulated
        carrying_amount = cost - accumulated

    return AssetDepreciationResult(
        asset_key=asset_key,
        acquisition_cost=cost,
        residual_value=residual,
        depreciable_base=base,
        useful_life_months=life,
        elapsed_months=elapsed,
        depreciation_for_period=period_depreciation,
        accumulated_depreciation=accumulated,
        carrying_amount=carrying_amount,
    )


def build_asset_depreciation_snapshot(
    result: AssetDepreciationResult,
) -> dict[str, object]:
    """Serialize a reproducible accounting-depreciation artifact."""

    return {
        "engine_version": ENGINE_VERSION,
        "method": "straight_line_book",
        "decimal_policy": {
            "precision": DECIMAL_PRECISION,
            "rounding": "ROUND_HALF_EVEN",
            "emin": ENGINE_CONTEXT.Emin,
            "emax": ENGINE_CONTEXT.Emax,
            "implicit_currency_rounding": False,
            "max_input_significant_digits": MAX_INPUT_SIGNIFICANT_DIGITS,
            "max_input_scale": MAX_INPUT_SCALE,
            "max_input_integer_digits": MAX_INPUT_INTEGER_DIGITS,
        },
        "asset_key": result.asset_key,
        "acquisition_cost": str(result.acquisition_cost),
        "residual_value": str(result.residual_value),
        "depreciable_base": str(result.depreciable_base),
        "useful_life_months": result.useful_life_months,
        "elapsed_months": result.elapsed_months,
        "depreciation_for_period": str(result.depreciation_for_period),
        "accumulated_depreciation": str(result.accumulated_depreciation),
        "carrying_amount": str(result.carrying_amount),
        "statutory_tax_rate_inferred": False,
        "tax_deductibility_inferred": False,
        "residual_value_inferred": False,
        "useful_life_inferred": False,
    }
