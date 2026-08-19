"""Decimal-only tax and social-security calculation primitives.

The kernel consumes resolved rule payloads. It never embeds tax rates or
monetary thresholds and never performs implicit currency rounding.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.rules_engine import ResolvedRule, build_rule_snapshot


class CalculationInputError(ValueError):
    """Raised when a caller supplies an invalid financial input."""


class CalculationRulePayloadError(RuntimeError):
    """Raised when a resolved rule cannot be used safely by the calculator."""


@dataclass(frozen=True)
class ProgressiveTaxResult:
    taxable_base: Decimal
    tax: Decimal
    marginal_rate: Decimal
    bracket_lower_bound: Decimal
    bracket_upper_bound: Decimal | None
    rule_snapshot: dict[str, object]


@dataclass(frozen=True)
class FlatTaxResult:
    taxable_base: Decimal
    rate: Decimal
    tax: Decimal
    rule_snapshot: dict[str, object]


@dataclass(frozen=True)
class SgkPremiumResult:
    declared_monthly_earnings: Decimal
    premium_base: Decimal
    minimum_premium_base: Decimal
    maximum_premium_base: Decimal
    employer_premium: Decimal
    employee_premium: Decimal
    combined_premium: Decimal
    limits_rule_snapshot: dict[str, object]
    rates_rule_snapshot: dict[str, object]


def _require_non_negative(value: Decimal, *, field: str) -> None:
    if not value.is_finite() or value < 0:
        raise CalculationInputError(f"{field} must be a finite non-negative Decimal")


def _decimal_string(value: object, *, path: str) -> Decimal:
    if not isinstance(value, str):
        raise CalculationRulePayloadError(f"{path} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise CalculationRulePayloadError(f"{path} is not a valid decimal string") from exc
    if not parsed.is_finite():
        raise CalculationRulePayloadError(f"{path} must be finite")
    return parsed


def _mapping(value: object, *, path: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CalculationRulePayloadError(f"{path} must be an object with string keys")
    return value


def _rate(value: object, *, path: str) -> Decimal:
    rate = _decimal_string(value, path=path)
    if rate < 0 or rate > 1:
        raise CalculationRulePayloadError(f"{path} must be between 0 and 1")
    return rate


def calculate_progressive_tax(
    taxable_base: Decimal,
    resolved_rule: ResolvedRule,
) -> ProgressiveTaxResult:
    """Apply a progressive tariff using exact Decimal arithmetic.

    Each band must provide `upper`, `base_tax`, and `rate`. `upper=None` is only
    valid for the final open-ended band. Official `base_tax` values are checked
    against the tax accumulated by prior bands before any result is returned.
    """

    _require_non_negative(taxable_base, field="taxable_base")
    raw_bands = resolved_rule.version.payload.get("bands")
    if not isinstance(raw_bands, list) or not raw_bands:
        raise CalculationRulePayloadError("payload.bands must be a non-empty list")

    lower = Decimal("0")
    expected_base_tax = Decimal("0")
    for index, raw_band in enumerate(raw_bands):
        band = _mapping(raw_band, path=f"payload.bands[{index}]")
        base_tax = _decimal_string(band.get("base_tax"), path=f"payload.bands[{index}].base_tax")
        rate = _rate(band.get("rate"), path=f"payload.bands[{index}].rate")
        if base_tax != expected_base_tax:
            raise CalculationRulePayloadError(
                f"payload.bands[{index}].base_tax breaks tariff continuity"
            )

        upper_value = band.get("upper")
        upper: Decimal | None
        if upper_value is None:
            upper = None
            if index != len(raw_bands) - 1:
                raise CalculationRulePayloadError("only the final tariff band may be open-ended")
        else:
            upper = _decimal_string(upper_value, path=f"payload.bands[{index}].upper")
            if upper <= lower:
                raise CalculationRulePayloadError("tariff upper bounds must increase strictly")

        if upper is None or taxable_base <= upper:
            tax = base_tax + (taxable_base - lower) * rate
            return ProgressiveTaxResult(
                taxable_base=taxable_base,
                tax=tax,
                marginal_rate=rate,
                bracket_lower_bound=lower,
                bracket_upper_bound=upper,
                rule_snapshot=build_rule_snapshot(resolved_rule),
            )

        expected_base_tax = base_tax + (upper - lower) * rate
        lower = upper

    raise CalculationRulePayloadError("tariff does not contain a terminal open-ended band")


def calculate_flat_tax(
    taxable_base: Decimal,
    resolved_rule: ResolvedRule,
) -> FlatTaxResult:
    """Apply a single rule-provided rate without implicit rounding."""

    _require_non_negative(taxable_base, field="taxable_base")
    rate = _rate(resolved_rule.version.payload.get("rate"), path="payload.rate")
    return FlatTaxResult(
        taxable_base=taxable_base,
        rate=rate,
        tax=taxable_base * rate,
        rule_snapshot=build_rule_snapshot(resolved_rule),
    )


def _premium_total(value: object, *, path: str) -> Decimal:
    if isinstance(value, str):
        return _rate(value, path=path)
    mapping = _mapping(value, path=path)
    total = _rate(mapping.get("total"), path=f"{path}.total")
    component_sum = Decimal("0")
    for key, component in mapping.items():
        if key == "total":
            continue
        component_sum += _rate(component, path=f"{path}.{key}")
    if component_sum != total:
        raise CalculationRulePayloadError(f"{path}.total does not equal component sum")
    return total


def calculate_sgk_4a_full_month_premiums(
    declared_monthly_earnings: Decimal,
    limits_rule: ResolvedRule,
    rates_rule: ResolvedRule,
) -> SgkPremiumResult:
    """Calculate full-month 4/a premiums using monthly PEK bounds.

    This primitive intentionally covers a full-month private-sector monthly PEK
    scenario only. Partial-month day-count logic and incentives require separate
    rules and must not be inferred here.
    """

    _require_non_negative(declared_monthly_earnings, field="declared_monthly_earnings")
    limits = limits_rule.version.payload
    minimum = _decimal_string(limits.get("monthly_min"), path="limits.monthly_min")
    maximum = _decimal_string(limits.get("monthly_max"), path="limits.monthly_max")
    if minimum <= 0 or maximum < minimum:
        raise CalculationRulePayloadError("invalid monthly PEK bounds")

    premium_base = min(max(declared_monthly_earnings, minimum), maximum)
    rates = rates_rule.version.payload
    employer_rate = _premium_total(rates.get("employer"), path="rates.employer")
    employee_rate = _premium_total(rates.get("employee"), path="rates.employee")
    combined_rate = _rate(rates.get("combined_total"), path="rates.combined_total")
    if employer_rate + employee_rate != combined_rate:
        raise CalculationRulePayloadError(
            "rates.combined_total does not equal employer + employee totals"
        )

    employer_premium = premium_base * employer_rate
    employee_premium = premium_base * employee_rate
    return SgkPremiumResult(
        declared_monthly_earnings=declared_monthly_earnings,
        premium_base=premium_base,
        minimum_premium_base=minimum,
        maximum_premium_base=maximum,
        employer_premium=employer_premium,
        employee_premium=employee_premium,
        combined_premium=employer_premium + employee_premium,
        limits_rule_snapshot=build_rule_snapshot(limits_rule),
        rates_rule_snapshot=build_rule_snapshot(rates_rule),
    )
