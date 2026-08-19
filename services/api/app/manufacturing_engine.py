"""Common manufacturing batch-cost primitives for food, textile, and basic metals.

The engine keeps quantity/yield math in one explicit output unit. BOM material
units may differ and are never added together to fabricate a physical yield.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.costing_engine import CostLine

ENGINE_VERSION = "manufacturing-core-v1"
ZERO = Decimal("0")
ONE = Decimal("1")

CONVERSION_CATEGORIES = frozenset(
    {
        "labor",
        "energy",
        "machine",
        "packaging",
        "subcontracting",
        "quality",
        "other",
    }
)


class ManufacturingInputError(ValueError):
    """Raised when manufacturing inputs violate the common batch contract."""


def _require_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise ManufacturingInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise ManufacturingInputError(f"{field} must be finite")
    return value


def _require_non_negative(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value < ZERO:
        raise ManufacturingInputError(f"{field} must be non-negative")
    return decimal_value


def _require_positive(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value <= ZERO:
        raise ManufacturingInputError(f"{field} must be positive")
    return decimal_value


def _require_key(value: str, *, field: str) -> None:
    if not value.strip():
        raise ManufacturingInputError(f"{field} must not be blank")


@dataclass(frozen=True)
class MaterialUsage:
    """Actual material consumed by a batch in its own measurement unit."""

    key: str
    quantity: Decimal
    unit_cost: Decimal
    unit: str

    def __post_init__(self) -> None:
        _require_key(self.key, field="material.key")
        _require_key(self.unit, field=f"material[{self.key}].unit")
        _require_non_negative(self.quantity, field=f"material[{self.key}].quantity")
        _require_non_negative(self.unit_cost, field=f"material[{self.key}].unit_cost")

    @property
    def total_cost(self) -> Decimal:
        return self.quantity * self.unit_cost


@dataclass(frozen=True)
class ConversionCost:
    """Manufacturing conversion cost such as labor, energy, or machine usage."""

    key: str
    category: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="conversion.key")
        if self.category not in CONVERSION_CATEGORIES:
            raise ManufacturingInputError(f"unsupported conversion category: {self.category}")
        _require_non_negative(self.amount, field=f"conversion[{self.key}].amount")


@dataclass(frozen=True)
class RecoveryCredit:
    """Explicit monetary recovery from scrap, by-product, or reusable output."""

    key: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="recovery.key")
        _require_non_negative(self.amount, field=f"recovery[{self.key}].amount")


@dataclass(frozen=True)
class ManufacturingBatchResult:
    """Exact batch-cost result before inventory/tax/legal valuation policies."""

    output_unit: str
    theoretical_output_quantity: Decimal
    good_output_quantity: Decimal
    loss_quantity: Decimal
    yield_ratio: Decimal
    loss_ratio: Decimal
    material_cost: Decimal
    conversion_cost: Decimal
    conversion_category_costs: tuple[tuple[str, Decimal], ...]
    gross_batch_cost: Decimal
    recovery_credit: Decimal
    net_batch_cost: Decimal
    unit_cost: Decimal


def _ensure_unique_keys(items: Iterable[MaterialUsage | ConversionCost | RecoveryCredit]) -> None:
    seen: set[str] = set()
    for item in items:
        if item.key in seen:
            raise ManufacturingInputError(f"duplicate manufacturing line key: {item.key}")
        seen.add(item.key)


def _category_totals(conversion_costs: Sequence[ConversionCost]) -> tuple[tuple[str, Decimal], ...]:
    totals: dict[str, Decimal] = {}
    for line in conversion_costs:
        totals[line.category] = totals.get(line.category, ZERO) + line.amount
    return tuple(sorted(totals.items()))


def calculate_manufacturing_batch(
    *,
    output_unit: str,
    theoretical_output_quantity: Decimal,
    good_output_quantity: Decimal,
    materials: Sequence[MaterialUsage],
    conversion_costs: Sequence[ConversionCost],
    recovery_credits: Sequence[RecoveryCredit] = (),
) -> ManufacturingBatchResult:
    """Calculate common batch yield and unit cost without hidden rounding."""

    _require_key(output_unit, field="output_unit")
    theoretical = _require_positive(
        theoretical_output_quantity,
        field="theoretical_output_quantity",
    )
    good = _require_positive(good_output_quantity, field="good_output_quantity")
    if good > theoretical:
        raise ManufacturingInputError(
            "good_output_quantity cannot exceed theoretical_output_quantity"
        )

    all_lines: tuple[MaterialUsage | ConversionCost | RecoveryCredit, ...] = (
        *materials,
        *conversion_costs,
        *recovery_credits,
    )
    _ensure_unique_keys(all_lines)

    material_cost = sum((line.total_cost for line in materials), ZERO)
    conversion_cost = sum((line.amount for line in conversion_costs), ZERO)
    gross_batch_cost = material_cost + conversion_cost
    recovery_credit = sum((line.amount for line in recovery_credits), ZERO)
    if recovery_credit > gross_batch_cost:
        raise ManufacturingInputError("recovery credit cannot exceed gross batch cost")

    net_batch_cost = gross_batch_cost - recovery_credit
    loss_quantity = theoretical - good
    yield_ratio = good / theoretical
    loss_ratio = ONE - yield_ratio
    unit_cost = net_batch_cost / good

    return ManufacturingBatchResult(
        output_unit=output_unit,
        theoretical_output_quantity=theoretical,
        good_output_quantity=good,
        loss_quantity=loss_quantity,
        yield_ratio=yield_ratio,
        loss_ratio=loss_ratio,
        material_cost=material_cost,
        conversion_cost=conversion_cost,
        conversion_category_costs=_category_totals(conversion_costs),
        gross_batch_cost=gross_batch_cost,
        recovery_credit=recovery_credit,
        net_batch_cost=net_batch_cost,
        unit_cost=unit_cost,
    )


def as_core_direct_cost(
    result: ManufacturingBatchResult,
    *,
    key: str = "manufacturing-batch",
) -> CostLine:
    """Bridge a completed manufacturing batch into the sector-neutral cost engine."""

    return CostLine(key=key, amount=result.net_batch_cost)


def build_manufacturing_snapshot(result: ManufacturingBatchResult) -> dict[str, object]:
    """Serialize exact manufacturing results using decimal strings."""

    return {
        "engine_version": ENGINE_VERSION,
        "output_unit": result.output_unit,
        "theoretical_output_quantity": str(result.theoretical_output_quantity),
        "good_output_quantity": str(result.good_output_quantity),
        "loss_quantity": str(result.loss_quantity),
        "yield_ratio": str(result.yield_ratio),
        "loss_ratio": str(result.loss_ratio),
        "material_cost": str(result.material_cost),
        "conversion_cost": str(result.conversion_cost),
        "conversion_category_costs": {
            category: str(amount) for category, amount in result.conversion_category_costs
        },
        "gross_batch_cost": str(result.gross_batch_cost),
        "recovery_credit": str(result.recovery_credit),
        "net_batch_cost": str(result.net_batch_cost),
        "unit_cost": str(result.unit_cost),
        "inventory_valuation_policy_applied": False,
        "tax_policy_applied": False,
    }
