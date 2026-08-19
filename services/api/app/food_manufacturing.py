"""Food-manufacturing adapter built on the common manufacturing core.

The adapter scales a recipe, makes loss categories explicit, and requires the
sellable package count/content to reconcile exactly to good product output.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.manufacturing_engine import (
    ConversionCost,
    ManufacturingBatchResult,
    MaterialUsage,
    RecoveryCredit,
    calculate_manufacturing_batch,
)

ENGINE_VERSION = "food-manufacturing-v1"
ZERO = Decimal("0")

FOOD_PROCESS_CATEGORIES = frozenset(
    {
        "labor",
        "energy",
        "cold_chain",
        "quality",
        "packaging",
        "subcontracting",
        "other",
    }
)

COMMON_PROCESS_CATEGORY = {
    "labor": "labor",
    "energy": "energy",
    "cold_chain": "other",
    "quality": "quality",
    "packaging": "packaging",
    "subcontracting": "subcontracting",
    "other": "other",
}


class FoodManufacturingInputError(ValueError):
    """Raised when packaged-food batch inputs fail reconciliation."""


def _require_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise FoodManufacturingInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise FoodManufacturingInputError(f"{field} must be finite")
    return value


def _require_non_negative(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value < ZERO:
        raise FoodManufacturingInputError(f"{field} must be non-negative")
    return decimal_value


def _require_positive(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value <= ZERO:
        raise FoodManufacturingInputError(f"{field} must be positive")
    return decimal_value


def _require_key(value: str, *, field: str) -> None:
    if not value.strip():
        raise FoodManufacturingInputError(f"{field} must not be blank")


def _require_positive_package_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FoodManufacturingInputError("package_count must be a positive integer")
    return value


@dataclass(frozen=True)
class RecipeIngredient:
    """Ingredient quantity and cost for one recipe unit."""

    key: str
    quantity_per_recipe: Decimal
    unit_cost: Decimal
    unit: str

    def __post_init__(self) -> None:
        _require_key(self.key, field="ingredient.key")
        _require_key(self.unit, field=f"ingredient[{self.key}].unit")
        _require_non_negative(
            self.quantity_per_recipe,
            field=f"ingredient[{self.key}].quantity_per_recipe",
        )
        _require_non_negative(self.unit_cost, field=f"ingredient[{self.key}].unit_cost")


@dataclass(frozen=True)
class PackageMaterial:
    """Packaging material consumption for one sellable package."""

    key: str
    quantity_per_package: Decimal
    unit_cost: Decimal
    unit: str

    def __post_init__(self) -> None:
        _require_key(self.key, field="package_material.key")
        _require_key(self.unit, field=f"package_material[{self.key}].unit")
        _require_non_negative(
            self.quantity_per_package,
            field=f"package_material[{self.key}].quantity_per_package",
        )
        _require_non_negative(self.unit_cost, field=f"package_material[{self.key}].unit_cost")


@dataclass(frozen=True)
class FoodProcessCost:
    """Food-specific process cost retained with its original semantic category."""

    key: str
    category: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="food_process.key")
        if self.category not in FOOD_PROCESS_CATEGORIES:
            raise FoodManufacturingInputError(f"unsupported food process category: {self.category}")
        _require_non_negative(self.amount, field=f"food_process[{self.key}].amount")


@dataclass(frozen=True)
class FoodBatchResult:
    """Packaged-food batch result layered on the common manufacturing result."""

    manufacturing: ManufacturingBatchResult
    recipe_batches: Decimal
    package_count: int
    package_content_quantity: Decimal
    packaged_output_quantity: Decimal
    process_loss_quantity: Decimal
    spoilage_quantity: Decimal
    quality_rejected_quantity: Decimal
    ingredient_cost: Decimal
    packaging_material_cost: Decimal
    food_process_category_costs: tuple[tuple[str, Decimal], ...]
    package_unit_cost: Decimal


def _ensure_unique_keys(
    items: Iterable[RecipeIngredient | PackageMaterial | FoodProcessCost],
) -> None:
    seen: set[str] = set()
    for item in items:
        if item.key in seen:
            raise FoodManufacturingInputError(f"duplicate food line key: {item.key}")
        seen.add(item.key)


def _food_process_totals(costs: Sequence[FoodProcessCost]) -> tuple[tuple[str, Decimal], ...]:
    totals: dict[str, Decimal] = {}
    for line in costs:
        totals[line.category] = totals.get(line.category, ZERO) + line.amount
    return tuple(sorted(totals.items()))


def calculate_food_batch(
    *,
    output_unit: str,
    recipe_batches: Decimal,
    theoretical_output_per_recipe: Decimal,
    ingredients: Sequence[RecipeIngredient],
    package_count: int,
    package_content_quantity: Decimal,
    package_materials: Sequence[PackageMaterial],
    process_costs: Sequence[FoodProcessCost],
    process_loss_quantity: Decimal = ZERO,
    spoilage_quantity: Decimal = ZERO,
    quality_rejected_quantity: Decimal = ZERO,
    recovery_credits: Sequence[RecoveryCredit] = (),
) -> FoodBatchResult:
    """Scale a packaged-food recipe and reconcile every unit of expected output."""

    _require_key(output_unit, field="output_unit")
    batches = _require_positive(recipe_batches, field="recipe_batches")
    theoretical_per_recipe = _require_positive(
        theoretical_output_per_recipe,
        field="theoretical_output_per_recipe",
    )
    packages = _require_positive_package_count(package_count)
    package_content = _require_positive(
        package_content_quantity,
        field="package_content_quantity",
    )
    process_loss = _require_non_negative(process_loss_quantity, field="process_loss_quantity")
    spoilage = _require_non_negative(spoilage_quantity, field="spoilage_quantity")
    quality_rejected = _require_non_negative(
        quality_rejected_quantity,
        field="quality_rejected_quantity",
    )

    _ensure_unique_keys((*ingredients, *package_materials, *process_costs))

    theoretical_output = theoretical_per_recipe * batches
    total_loss = process_loss + spoilage + quality_rejected
    if total_loss >= theoretical_output:
        raise FoodManufacturingInputError("food losses must leave positive good output")
    good_output = theoretical_output - total_loss
    packaged_output = Decimal(packages) * package_content
    if packaged_output != good_output:
        raise FoodManufacturingInputError(
            "package_count * package_content_quantity must equal good product output"
        )

    ingredient_usages = tuple(
        MaterialUsage(
            key=f"ingredient:{item.key}",
            quantity=item.quantity_per_recipe * batches,
            unit_cost=item.unit_cost,
            unit=item.unit,
        )
        for item in ingredients
    )
    packaging_usages = tuple(
        MaterialUsage(
            key=f"package:{item.key}",
            quantity=item.quantity_per_package * Decimal(packages),
            unit_cost=item.unit_cost,
            unit=item.unit,
        )
        for item in package_materials
    )
    common_process_costs = tuple(
        ConversionCost(
            key=f"food-process:{item.key}",
            category=COMMON_PROCESS_CATEGORY[item.category],
            amount=item.amount,
        )
        for item in process_costs
    )

    manufacturing = calculate_manufacturing_batch(
        output_unit=output_unit,
        theoretical_output_quantity=theoretical_output,
        good_output_quantity=good_output,
        materials=(*ingredient_usages, *packaging_usages),
        conversion_costs=common_process_costs,
        recovery_credits=recovery_credits,
    )

    ingredient_cost = sum((item.total_cost for item in ingredient_usages), ZERO)
    packaging_cost = sum((item.total_cost for item in packaging_usages), ZERO)
    package_unit_cost = manufacturing.net_batch_cost / Decimal(packages)

    return FoodBatchResult(
        manufacturing=manufacturing,
        recipe_batches=batches,
        package_count=packages,
        package_content_quantity=package_content,
        packaged_output_quantity=packaged_output,
        process_loss_quantity=process_loss,
        spoilage_quantity=spoilage,
        quality_rejected_quantity=quality_rejected,
        ingredient_cost=ingredient_cost,
        packaging_material_cost=packaging_cost,
        food_process_category_costs=_food_process_totals(process_costs),
        package_unit_cost=package_unit_cost,
    )


def build_food_snapshot(result: FoodBatchResult) -> dict[str, object]:
    """Serialize exact packaged-food results without claiming regulatory validation."""

    return {
        "engine_version": ENGINE_VERSION,
        "recipe_batches": str(result.recipe_batches),
        "package_count": result.package_count,
        "package_content_quantity": str(result.package_content_quantity),
        "packaged_output_quantity": str(result.packaged_output_quantity),
        "process_loss_quantity": str(result.process_loss_quantity),
        "spoilage_quantity": str(result.spoilage_quantity),
        "quality_rejected_quantity": str(result.quality_rejected_quantity),
        "ingredient_cost": str(result.ingredient_cost),
        "packaging_material_cost": str(result.packaging_material_cost),
        "food_process_category_costs": {
            category: str(amount) for category, amount in result.food_process_category_costs
        },
        "package_unit_cost": str(result.package_unit_cost),
        "common_manufacturing_unit_cost": str(result.manufacturing.unit_cost),
        "food_regulatory_policy_applied": False,
        "shelf_life_policy_applied": False,
        "inventory_valuation_policy_applied": False,
    }
