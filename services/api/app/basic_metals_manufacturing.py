"""Basic-metals manufacturing adapter built on the common batch-cost core.

The adapter keeps engineering output, losses, material use, energy use, and
recovered-scrap value explicit. It does not infer output mass from mixed inputs.
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

ENGINE_VERSION = "basic-metals-manufacturing-v1"
ZERO = Decimal("0")

METAL_MATERIAL_CATEGORIES = frozenset(
    {
        "primary_metal",
        "recycled_charge",
        "alloy",
        "flux",
        "electrode",
        "refractory",
        "consumable",
        "packaging",
        "other",
    }
)

METAL_ENERGY_STAGES = frozenset(
    {
        "melting",
        "reheating",
        "heat_treatment",
        "casting",
        "rolling",
        "other",
    }
)

METAL_PROCESS_STAGES = frozenset(
    {
        "melting",
        "casting",
        "rolling",
        "forging",
        "heat_treatment",
        "machining",
        "finishing",
        "quality",
        "packaging",
        "other",
    }
)


class BasicMetalsInputError(ValueError):
    """Raised when basic-metals inputs violate explicit engineering contracts."""


def _require_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise BasicMetalsInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise BasicMetalsInputError(f"{field} must be finite")
    return value


def _require_non_negative(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value < ZERO:
        raise BasicMetalsInputError(f"{field} must be non-negative")
    return decimal_value


def _require_positive(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value <= ZERO:
        raise BasicMetalsInputError(f"{field} must be positive")
    return decimal_value


def _require_key(value: str, *, field: str) -> None:
    if not value.strip():
        raise BasicMetalsInputError(f"{field} must not be blank")


@dataclass(frozen=True)
class MetalMaterial:
    """Actual metal/alloy/consumable usage in its native measurement unit."""

    key: str
    category: str
    quantity: Decimal
    unit_cost: Decimal
    unit: str

    def __post_init__(self) -> None:
        _require_key(self.key, field="metal_material.key")
        _require_key(self.unit, field=f"metal_material[{self.key}].unit")
        if self.category not in METAL_MATERIAL_CATEGORIES:
            raise BasicMetalsInputError(f"unsupported metal material category: {self.category}")
        _require_non_negative(self.quantity, field=f"metal_material[{self.key}].quantity")
        _require_non_negative(self.unit_cost, field=f"metal_material[{self.key}].unit_cost")


@dataclass(frozen=True)
class MetalEnergyUsage:
    """Metered energy/fuel usage priced explicitly for one process stage."""

    key: str
    stage: str
    quantity: Decimal
    unit_rate: Decimal
    unit: str

    def __post_init__(self) -> None:
        _require_key(self.key, field="metal_energy.key")
        _require_key(self.unit, field=f"metal_energy[{self.key}].unit")
        if self.stage not in METAL_ENERGY_STAGES:
            raise BasicMetalsInputError(f"unsupported metal energy stage: {self.stage}")
        _require_non_negative(self.quantity, field=f"metal_energy[{self.key}].quantity")
        _require_non_negative(self.unit_rate, field=f"metal_energy[{self.key}].unit_rate")

    @property
    def total_cost(self) -> Decimal:
        return self.quantity * self.unit_rate


@dataclass(frozen=True)
class MetalProcessCost:
    """Non-energy process cost with explicit stage and common cost category."""

    key: str
    stage: str
    cost_category: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="metal_process.key")
        if self.stage not in METAL_PROCESS_STAGES:
            raise BasicMetalsInputError(f"unsupported metal process stage: {self.stage}")
        if self.cost_category not in CONVERSION_CATEGORIES:
            raise BasicMetalsInputError(f"unsupported metal cost category: {self.cost_category}")
        _require_non_negative(self.amount, field=f"metal_process[{self.key}].amount")


@dataclass(frozen=True)
class RecoveredScrap:
    """Recovered metal/scrap quantity with an explicit management unit value."""

    key: str
    quantity: Decimal
    unit_value: Decimal
    unit: str

    def __post_init__(self) -> None:
        _require_key(self.key, field="recovered_scrap.key")
        _require_key(self.unit, field=f"recovered_scrap[{self.key}].unit")
        _require_non_negative(self.quantity, field=f"recovered_scrap[{self.key}].quantity")
        _require_non_negative(self.unit_value, field=f"recovered_scrap[{self.key}].unit_value")

    @property
    def total_credit(self) -> Decimal:
        return self.quantity * self.unit_value


@dataclass(frozen=True)
class BasicMetalsBatchResult:
    """Engineering-yield and management-cost result for a basic-metals batch."""

    manufacturing: ManufacturingBatchResult
    melt_loss_quantity: Decimal
    slag_loss_quantity: Decimal
    quality_reject_quantity: Decimal
    material_category_costs: tuple[tuple[str, Decimal], ...]
    energy_stage_costs: tuple[tuple[str, Decimal], ...]
    process_stage_costs: tuple[tuple[str, Decimal], ...]
    recovered_scrap_credit: Decimal
    finished_output_unit_cost: Decimal


def _ensure_unique_keys(
    items: Iterable[MetalMaterial | MetalEnergyUsage | MetalProcessCost | RecoveredScrap],
) -> None:
    seen: set[str] = set()
    for item in items:
        if item.key in seen:
            raise BasicMetalsInputError(f"duplicate basic-metals line key: {item.key}")
        seen.add(item.key)


def _material_category_totals(
    materials: Sequence[MetalMaterial],
) -> tuple[tuple[str, Decimal], ...]:
    totals: dict[str, Decimal] = {}
    for line in materials:
        amount = line.quantity * line.unit_cost
        totals[line.category] = totals.get(line.category, ZERO) + amount
    return tuple(sorted(totals.items()))


def _energy_stage_totals(
    energy_usages: Sequence[MetalEnergyUsage],
) -> tuple[tuple[str, Decimal], ...]:
    totals: dict[str, Decimal] = {}
    for line in energy_usages:
        totals[line.stage] = totals.get(line.stage, ZERO) + line.total_cost
    return tuple(sorted(totals.items()))


def _process_stage_totals(
    process_costs: Sequence[MetalProcessCost],
) -> tuple[tuple[str, Decimal], ...]:
    totals: dict[str, Decimal] = {}
    for line in process_costs:
        totals[line.stage] = totals.get(line.stage, ZERO) + line.amount
    return tuple(sorted(totals.items()))


def calculate_basic_metals_batch(
    *,
    output_unit: str,
    theoretical_output_quantity: Decimal,
    melt_loss_quantity: Decimal,
    slag_loss_quantity: Decimal,
    quality_reject_quantity: Decimal,
    materials: Sequence[MetalMaterial],
    energy_usages: Sequence[MetalEnergyUsage],
    process_costs: Sequence[MetalProcessCost],
    recovered_scrap: Sequence[RecoveredScrap] = (),
) -> BasicMetalsBatchResult:
    """Calculate metal yield and batch cost from explicit engineering inputs."""

    _require_key(output_unit, field="output_unit")
    theoretical = _require_positive(
        theoretical_output_quantity,
        field="theoretical_output_quantity",
    )
    melt_loss = _require_non_negative(melt_loss_quantity, field="melt_loss_quantity")
    slag_loss = _require_non_negative(slag_loss_quantity, field="slag_loss_quantity")
    quality_reject = _require_non_negative(
        quality_reject_quantity,
        field="quality_reject_quantity",
    )

    total_loss = melt_loss + slag_loss + quality_reject
    if total_loss >= theoretical:
        raise BasicMetalsInputError("metal losses must leave positive good output")
    good_output = theoretical - total_loss

    _ensure_unique_keys((*materials, *energy_usages, *process_costs, *recovered_scrap))

    common_materials = tuple(
        MaterialUsage(
            key=f"metal-material:{item.key}",
            quantity=item.quantity,
            unit_cost=item.unit_cost,
            unit=item.unit,
        )
        for item in materials
    )
    energy_costs = tuple(
        ConversionCost(
            key=f"metal-energy:{item.key}",
            category="energy",
            amount=item.total_cost,
        )
        for item in energy_usages
    )
    common_process_costs = tuple(
        ConversionCost(
            key=f"metal-process:{item.key}",
            category=item.cost_category,
            amount=item.amount,
        )
        for item in process_costs
    )
    recovery_credits = tuple(
        RecoveryCredit(key=f"metal-recovery:{item.key}", amount=item.total_credit)
        for item in recovered_scrap
    )

    manufacturing = calculate_manufacturing_batch(
        output_unit=output_unit,
        theoretical_output_quantity=theoretical,
        good_output_quantity=good_output,
        materials=common_materials,
        conversion_costs=(*energy_costs, *common_process_costs),
        recovery_credits=recovery_credits,
    )
    recovered_credit = sum((item.total_credit for item in recovered_scrap), ZERO)

    return BasicMetalsBatchResult(
        manufacturing=manufacturing,
        melt_loss_quantity=melt_loss,
        slag_loss_quantity=slag_loss,
        quality_reject_quantity=quality_reject,
        material_category_costs=_material_category_totals(materials),
        energy_stage_costs=_energy_stage_totals(energy_usages),
        process_stage_costs=_process_stage_totals(process_costs),
        recovered_scrap_credit=recovered_credit,
        finished_output_unit_cost=manufacturing.unit_cost,
    )


def build_basic_metals_snapshot(result: BasicMetalsBatchResult) -> dict[str, object]:
    """Serialize exact management results without claiming legal waste valuation."""

    return {
        "engine_version": ENGINE_VERSION,
        "output_unit": result.manufacturing.output_unit,
        "theoretical_output_quantity": str(result.manufacturing.theoretical_output_quantity),
        "good_output_quantity": str(result.manufacturing.good_output_quantity),
        "melt_loss_quantity": str(result.melt_loss_quantity),
        "slag_loss_quantity": str(result.slag_loss_quantity),
        "quality_reject_quantity": str(result.quality_reject_quantity),
        "yield_ratio": str(result.manufacturing.yield_ratio),
        "material_category_costs": {
            category: str(amount) for category, amount in result.material_category_costs
        },
        "energy_stage_costs": {stage: str(amount) for stage, amount in result.energy_stage_costs},
        "process_stage_costs": {stage: str(amount) for stage, amount in result.process_stage_costs},
        "recovered_scrap_credit": str(result.recovered_scrap_credit),
        "finished_output_unit_cost": str(result.finished_output_unit_cost),
        "inventory_valuation_policy_applied": False,
        "tax_waste_policy_applied": False,
        "scrap_market_value_inferred": False,
    }
