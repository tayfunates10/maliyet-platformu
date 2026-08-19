"""Regression tests for the packaged-food manufacturing adapter."""

from decimal import Decimal

import pytest

from app.food_manufacturing import (
    FoodManufacturingInputError,
    FoodProcessCost,
    PackageMaterial,
    RecipeIngredient,
    build_food_snapshot,
    calculate_food_batch,
)
from app.manufacturing_engine import RecoveryCredit


def test_packaged_food_recipe_scales_and_reconciles_losses() -> None:
    result = calculate_food_batch(
        output_unit="kg",
        recipe_batches=Decimal("2"),
        theoretical_output_per_recipe=Decimal("100"),
        ingredients=(
            RecipeIngredient("flour", Decimal("50"), Decimal("8.00"), "kg"),
            RecipeIngredient("oil", Decimal("10"), Decimal("20.00"), "kg"),
        ),
        package_count=380,
        package_content_quantity=Decimal("0.5"),
        package_materials=(
            PackageMaterial("pouch", Decimal("1"), Decimal("0.50"), "piece"),
            PackageMaterial("label", Decimal("1"), Decimal("0.10"), "piece"),
        ),
        process_costs=(
            FoodProcessCost("labor", "labor", Decimal("300.00")),
            FoodProcessCost("energy", "energy", Decimal("200.00")),
            FoodProcessCost("cold", "cold_chain", Decimal("100.00")),
            FoodProcessCost("quality", "quality", Decimal("50.00")),
        ),
        process_loss_quantity=Decimal("4"),
        spoilage_quantity=Decimal("3"),
        quality_rejected_quantity=Decimal("3"),
        recovery_credits=(RecoveryCredit("byproduct", Decimal("50.00")),),
    )

    assert result.manufacturing.theoretical_output_quantity == Decimal("200")
    assert result.manufacturing.good_output_quantity == Decimal("190")
    assert result.manufacturing.yield_ratio == Decimal("0.95")
    assert result.ingredient_cost == Decimal("1200.00")
    assert result.packaging_material_cost == Decimal("228.00")
    assert result.manufacturing.conversion_cost == Decimal("650.00")
    assert result.manufacturing.gross_batch_cost == Decimal("2078.00")
    assert result.manufacturing.net_batch_cost == Decimal("2028.00")
    assert result.package_unit_cost == Decimal("2028.00") / Decimal("380")


def test_package_output_must_equal_good_product_output() -> None:
    with pytest.raises(FoodManufacturingInputError, match="must equal good product output"):
        calculate_food_batch(
            output_unit="kg",
            recipe_batches=Decimal("1"),
            theoretical_output_per_recipe=Decimal("10"),
            ingredients=(),
            package_count=9,
            package_content_quantity=Decimal("1"),
            package_materials=(),
            process_costs=(),
        )


def test_recipe_ingredient_and_packaging_quantities_scale_exactly() -> None:
    result = calculate_food_batch(
        output_unit="kg",
        recipe_batches=Decimal("3"),
        theoretical_output_per_recipe=Decimal("10"),
        ingredients=(RecipeIngredient("ingredient", Decimal("2"), Decimal("4.00"), "kg"),),
        package_count=60,
        package_content_quantity=Decimal("0.5"),
        package_materials=(PackageMaterial("cup", Decimal("1"), Decimal("0.25"), "piece"),),
        process_costs=(),
    )
    assert result.ingredient_cost == Decimal("24.00")
    assert result.packaging_material_cost == Decimal("15.00")
    assert result.manufacturing.net_batch_cost == Decimal("39.00")


def test_losses_cannot_consume_entire_theoretical_output() -> None:
    with pytest.raises(FoodManufacturingInputError, match="leave positive good output"):
        calculate_food_batch(
            output_unit="kg",
            recipe_batches=Decimal("1"),
            theoretical_output_per_recipe=Decimal("10"),
            ingredients=(),
            package_count=1,
            package_content_quantity=Decimal("1"),
            package_materials=(),
            process_costs=(),
            spoilage_quantity=Decimal("10"),
        )


def test_package_count_must_be_positive_integer() -> None:
    with pytest.raises(FoodManufacturingInputError, match="positive integer"):
        calculate_food_batch(
            output_unit="kg",
            recipe_batches=Decimal("1"),
            theoretical_output_per_recipe=Decimal("10"),
            ingredients=(),
            package_count=0,
            package_content_quantity=Decimal("1"),
            package_materials=(),
            process_costs=(),
        )


def test_runtime_rejects_float_package_content() -> None:
    with pytest.raises(FoodManufacturingInputError, match="must be Decimal"):
        calculate_food_batch(
            output_unit="kg",
            recipe_batches=Decimal("1"),
            theoretical_output_per_recipe=Decimal("10"),
            ingredients=(),
            package_count=10,
            package_content_quantity=1.0,  # type: ignore[arg-type]
            package_materials=(),
            process_costs=(),
        )


def test_duplicate_key_across_food_input_groups_fails_closed() -> None:
    with pytest.raises(FoodManufacturingInputError, match="duplicate food line key"):
        calculate_food_batch(
            output_unit="kg",
            recipe_batches=Decimal("1"),
            theoretical_output_per_recipe=Decimal("10"),
            ingredients=(RecipeIngredient("shared", Decimal("1"), Decimal("1.00"), "kg"),),
            package_count=10,
            package_content_quantity=Decimal("1"),
            package_materials=(PackageMaterial("shared", Decimal("1"), Decimal("0.10"), "piece"),),
            process_costs=(),
        )


def test_food_process_categories_preserve_cold_chain_semantics() -> None:
    result = calculate_food_batch(
        output_unit="kg",
        recipe_batches=Decimal("1"),
        theoretical_output_per_recipe=Decimal("10"),
        ingredients=(),
        package_count=10,
        package_content_quantity=Decimal("1"),
        package_materials=(),
        process_costs=(
            FoodProcessCost("cold-1", "cold_chain", Decimal("25.00")),
            FoodProcessCost("cold-2", "cold_chain", Decimal("15.00")),
            FoodProcessCost("quality", "quality", Decimal("10.00")),
        ),
    )
    assert result.food_process_category_costs == (
        ("cold_chain", Decimal("40.00")),
        ("quality", Decimal("10.00")),
    )
    assert result.manufacturing.conversion_cost == Decimal("50.00")


def test_snapshot_does_not_claim_food_regulatory_or_shelf_life_validation() -> None:
    result = calculate_food_batch(
        output_unit="kg",
        recipe_batches=Decimal("1"),
        theoretical_output_per_recipe=Decimal("10"),
        ingredients=(),
        package_count=10,
        package_content_quantity=Decimal("1"),
        package_materials=(),
        process_costs=(),
    )
    snapshot = build_food_snapshot(result)
    assert snapshot["food_regulatory_policy_applied"] is False
    assert snapshot["shelf_life_policy_applied"] is False
    assert snapshot["inventory_valuation_policy_applied"] is False
