"""Textile manufacturing adapter built on the common manufacturing core.

Material quantities remain in their own units. Finished-piece yield is reconciled
only in piece counts, so metres, kilograms, and accessories are never mixed.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.manufacturing_engine import (
    CONVERSION_CATEGORIES,
    ConversionCost,
    ManufacturingBatchResult,
    MaterialUsage,
    RecoveryCredit,
    calculate_manufacturing_batch,
)

ENGINE_VERSION = "textile-manufacturing-v1"
ZERO = Decimal("0")

TEXTILE_MATERIAL_CATEGORIES = frozenset(
    {
        "fabric",
        "yarn",
        "lining",
        "accessory",
        "chemical",
        "packaging",
        "other",
    }
)

TEXTILE_PROCESS_STAGES = frozenset(
    {
        "cutting",
        "sewing",
        "dyeing",
        "printing",
        "embroidery",
        "finishing",
        "ironing",
        "packaging",
        "quality",
        "other",
    }
)


class TextileManufacturingInputError(ValueError):
    """Raised when textile batch inputs violate explicit reconciliation rules."""


def _require_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TextileManufacturingInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise TextileManufacturingInputError(f"{field} must be finite")
    return value


def _require_non_negative(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value < ZERO:
        raise TextileManufacturingInputError(f"{field} must be non-negative")
    return decimal_value


def _require_key(value: str, *, field: str) -> None:
    if not value.strip():
        raise TextileManufacturingInputError(f"{field} must not be blank")


def _require_positive_count(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TextileManufacturingInputError(f"{field} must be a positive integer")
    return value


def _require_non_negative_count(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TextileManufacturingInputError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class TextileMaterial:
    """Actual textile material consumption in its native measurement unit."""

    key: str
    category: str
    quantity: Decimal
    unit_cost: Decimal
    unit: str

    def __post_init__(self) -> None:
        _require_key(self.key, field="textile_material.key")
        _require_key(self.unit, field=f"textile_material[{self.key}].unit")
        if self.category not in TEXTILE_MATERIAL_CATEGORIES:
            raise TextileManufacturingInputError(
                f"unsupported textile material category: {self.category}"
            )
        _require_non_negative(self.quantity, field=f"textile_material[{self.key}].quantity")
        _require_non_negative(self.unit_cost, field=f"textile_material[{self.key}].unit_cost")


@dataclass(frozen=True)
class TextileProcessCost:
    """Process-stage cost with an explicit common manufacturing cost category."""

    key: str
    stage: str
    cost_category: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="textile_process.key")
        if self.stage not in TEXTILE_PROCESS_STAGES:
            raise TextileManufacturingInputError(f"unsupported textile process stage: {self.stage}")
        if self.cost_category not in CONVERSION_CATEGORIES:
            raise TextileManufacturingInputError(
                f"unsupported textile cost category: {self.cost_category}"
            )
        _require_non_negative(self.amount, field=f"textile_process[{self.key}].amount")


@dataclass(frozen=True)
class TextileBatchResult:
    """Finished-piece textile result layered on common manufacturing costing."""

    manufacturing: ManufacturingBatchResult
    theoretical_piece_count: int
    good_piece_count: int
    cutting_reject_count: int
    quality_reject_count: int
    ordered_piece_count: int
    surplus_good_piece_count: int
    material_category_costs: tuple[tuple[str, Decimal], ...]
    process_stage_costs: tuple[tuple[str, Decimal], ...]
    finished_piece_unit_cost: Decimal
    management_order_cost: Decimal


def _ensure_unique_keys(items: Iterable[TextileMaterial | TextileProcessCost]) -> None:
    seen: set[str] = set()
    for item in items:
        if item.key in seen:
            raise TextileManufacturingInputError(f"duplicate textile line key: {item.key}")
        seen.add(item.key)


def _material_category_totals(
    materials: Sequence[TextileMaterial],
) -> tuple[tuple[str, Decimal], ...]:
    totals: dict[str, Decimal] = {}
    for line in materials:
        amount = line.quantity * line.unit_cost
        totals[line.category] = totals.get(line.category, ZERO) + amount
    return tuple(sorted(totals.items()))


def _process_stage_totals(
    process_costs: Sequence[TextileProcessCost],
) -> tuple[tuple[str, Decimal], ...]:
    totals: dict[str, Decimal] = {}
    for line in process_costs:
        totals[line.stage] = totals.get(line.stage, ZERO) + line.amount
    return tuple(sorted(totals.items()))


def calculate_textile_batch(
    *,
    theoretical_piece_count: int,
    cutting_reject_count: int,
    quality_reject_count: int,
    ordered_piece_count: int,
    materials: Sequence[TextileMaterial],
    process_costs: Sequence[TextileProcessCost],
    recovery_credits: Sequence[RecoveryCredit] = (),
) -> TextileBatchResult:
    """Calculate finished-piece textile yield and cost without unit fabrication."""

    theoretical = _require_positive_count(
        theoretical_piece_count,
        field="theoretical_piece_count",
    )
    cutting_reject = _require_non_negative_count(
        cutting_reject_count,
        field="cutting_reject_count",
    )
    quality_reject = _require_non_negative_count(
        quality_reject_count,
        field="quality_reject_count",
    )
    ordered = _require_positive_count(ordered_piece_count, field="ordered_piece_count")

    rejected = cutting_reject + quality_reject
    if rejected >= theoretical:
        raise TextileManufacturingInputError("textile rejects must leave positive good output")
    good = theoretical - rejected
    if ordered > good:
        raise TextileManufacturingInputError("ordered_piece_count cannot exceed good_piece_count")

    _ensure_unique_keys((*materials, *process_costs))

    common_materials = tuple(
        MaterialUsage(
            key=f"textile-material:{item.key}",
            quantity=item.quantity,
            unit_cost=item.unit_cost,
            unit=item.unit,
        )
        for item in materials
    )
    common_process_costs = tuple(
        ConversionCost(
            key=f"textile-process:{item.key}",
            category=item.cost_category,
            amount=item.amount,
        )
        for item in process_costs
    )

    manufacturing = calculate_manufacturing_batch(
        output_unit="piece",
        theoretical_output_quantity=Decimal(theoretical),
        good_output_quantity=Decimal(good),
        materials=common_materials,
        conversion_costs=common_process_costs,
        recovery_credits=recovery_credits,
    )
    finished_piece_unit_cost = manufacturing.unit_cost
    management_order_cost = finished_piece_unit_cost * Decimal(ordered)

    return TextileBatchResult(
        manufacturing=manufacturing,
        theoretical_piece_count=theoretical,
        good_piece_count=good,
        cutting_reject_count=cutting_reject,
        quality_reject_count=quality_reject,
        ordered_piece_count=ordered,
        surplus_good_piece_count=good - ordered,
        material_category_costs=_material_category_totals(materials),
        process_stage_costs=_process_stage_totals(process_costs),
        finished_piece_unit_cost=finished_piece_unit_cost,
        management_order_cost=management_order_cost,
    )


def build_textile_snapshot(result: TextileBatchResult) -> dict[str, object]:
    """Serialize exact management costing without claiming legal stock valuation."""

    return {
        "engine_version": ENGINE_VERSION,
        "theoretical_piece_count": result.theoretical_piece_count,
        "good_piece_count": result.good_piece_count,
        "cutting_reject_count": result.cutting_reject_count,
        "quality_reject_count": result.quality_reject_count,
        "ordered_piece_count": result.ordered_piece_count,
        "surplus_good_piece_count": result.surplus_good_piece_count,
        "material_category_costs": {
            category: str(amount) for category, amount in result.material_category_costs
        },
        "process_stage_costs": {stage: str(amount) for stage, amount in result.process_stage_costs},
        "finished_piece_unit_cost": str(result.finished_piece_unit_cost),
        "management_order_cost": str(result.management_order_cost),
        "order_cost_is_management_allocation": True,
        "inventory_valuation_policy_applied": False,
        "tax_waste_policy_applied": False,
    }
