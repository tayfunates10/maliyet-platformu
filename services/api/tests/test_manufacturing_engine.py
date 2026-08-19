"""Regression tests for the common manufacturing batch-cost engine."""

from decimal import Decimal

import pytest

from app.manufacturing_engine import (
    ConversionCost,
    ManufacturingInputError,
    MaterialUsage,
    RecoveryCredit,
    as_core_direct_cost,
    build_manufacturing_snapshot,
    calculate_manufacturing_batch,
)


def test_food_like_batch_calculates_yield_and_exact_unit_cost() -> None:
    result = calculate_manufacturing_batch(
        output_unit="kg",
        theoretical_output_quantity=Decimal("1000"),
        good_output_quantity=Decimal("950"),
        materials=(
            MaterialUsage("flour", Decimal("500"), Decimal("8.00"), "kg"),
            MaterialUsage("oil", Decimal("100"), Decimal("20.00"), "kg"),
        ),
        conversion_costs=(
            ConversionCost("labor", "labor", Decimal("1500.00")),
            ConversionCost("energy", "energy", Decimal("1000.00")),
            ConversionCost("packaging", "packaging", Decimal("500.00")),
        ),
        recovery_credits=(RecoveryCredit("recoverable-byproduct", Decimal("200.00")),),
    )

    assert result.material_cost == Decimal("6000.00")
    assert result.conversion_cost == Decimal("3000.00")
    assert result.gross_batch_cost == Decimal("9000.00")
    assert result.recovery_credit == Decimal("200.00")
    assert result.net_batch_cost == Decimal("8800.00")
    assert result.loss_quantity == Decimal("50")
    assert result.yield_ratio == Decimal("0.95")
    assert result.loss_ratio == Decimal("0.05")
    assert result.unit_cost == Decimal("8800.00") / Decimal("950")


def test_material_units_are_costed_individually_not_physically_summed() -> None:
    result = calculate_manufacturing_batch(
        output_unit="piece",
        theoretical_output_quantity=Decimal("100"),
        good_output_quantity=Decimal("90"),
        materials=(
            MaterialUsage("fabric", Decimal("220"), Decimal("5.00"), "meter"),
            MaterialUsage("zipper", Decimal("100"), Decimal("1.50"), "piece"),
        ),
        conversion_costs=(ConversionCost("sewing", "labor", Decimal("900.00")),),
    )

    assert result.material_cost == Decimal("1250.00")
    assert result.yield_ratio == Decimal("0.9")
    assert result.good_output_quantity == Decimal("90")


def test_recovered_scrap_credit_reduces_metal_batch_cost() -> None:
    result = calculate_manufacturing_batch(
        output_unit="kg",
        theoretical_output_quantity=Decimal("1000"),
        good_output_quantity=Decimal("920"),
        materials=(MaterialUsage("metal-charge", Decimal("1000"), Decimal("30.00"), "kg"),),
        conversion_costs=(
            ConversionCost("furnace", "energy", Decimal("5000.00")),
            ConversionCost("machine", "machine", Decimal("2000.00")),
        ),
        recovery_credits=(RecoveryCredit("scrap-credit", Decimal("2400.00")),),
    )

    assert result.gross_batch_cost == Decimal("37000.00")
    assert result.net_batch_cost == Decimal("34600.00")
    assert result.unit_cost == Decimal("34600.00") / Decimal("920")


def test_good_output_cannot_exceed_theoretical_output() -> None:
    with pytest.raises(ManufacturingInputError, match="cannot exceed"):
        calculate_manufacturing_batch(
            output_unit="kg",
            theoretical_output_quantity=Decimal("100"),
            good_output_quantity=Decimal("100.01"),
            materials=(),
            conversion_costs=(),
        )


def test_good_output_must_be_positive() -> None:
    with pytest.raises(ManufacturingInputError, match="must be positive"):
        calculate_manufacturing_batch(
            output_unit="kg",
            theoretical_output_quantity=Decimal("100"),
            good_output_quantity=Decimal("0"),
            materials=(),
            conversion_costs=(),
        )


def test_recovery_credit_cannot_make_batch_cost_negative() -> None:
    with pytest.raises(ManufacturingInputError, match="cannot exceed"):
        calculate_manufacturing_batch(
            output_unit="kg",
            theoretical_output_quantity=Decimal("10"),
            good_output_quantity=Decimal("10"),
            materials=(MaterialUsage("material", Decimal("1"), Decimal("100.00"), "kg"),),
            conversion_costs=(),
            recovery_credits=(RecoveryCredit("credit", Decimal("100.01")),),
        )


def test_duplicate_line_keys_fail_closed_across_cost_types() -> None:
    with pytest.raises(ManufacturingInputError, match="duplicate"):
        calculate_manufacturing_batch(
            output_unit="piece",
            theoretical_output_quantity=Decimal("10"),
            good_output_quantity=Decimal("10"),
            materials=(MaterialUsage("shared", Decimal("1"), Decimal("5.00"), "kg"),),
            conversion_costs=(ConversionCost("shared", "labor", Decimal("5.00")),),
        )


def test_runtime_rejects_float_material_quantity() -> None:
    with pytest.raises(ManufacturingInputError, match="must be Decimal"):
        MaterialUsage("material", 1.5, Decimal("5.00"), "kg")  # type: ignore[arg-type]


def test_conversion_category_totals_are_deterministic() -> None:
    result = calculate_manufacturing_batch(
        output_unit="piece",
        theoretical_output_quantity=Decimal("10"),
        good_output_quantity=Decimal("10"),
        materials=(),
        conversion_costs=(
            ConversionCost("machine-2", "machine", Decimal("30.00")),
            ConversionCost("labor-1", "labor", Decimal("20.00")),
            ConversionCost("machine-1", "machine", Decimal("10.00")),
        ),
    )
    assert result.conversion_category_costs == (
        ("labor", Decimal("20.00")),
        ("machine", Decimal("40.00")),
    )


def test_manufacturing_result_bridges_into_core_direct_cost() -> None:
    result = calculate_manufacturing_batch(
        output_unit="piece",
        theoretical_output_quantity=Decimal("10"),
        good_output_quantity=Decimal("10"),
        materials=(MaterialUsage("material", Decimal("10"), Decimal("3.00"), "piece"),),
        conversion_costs=(ConversionCost("labor", "labor", Decimal("20.00")),),
    )
    direct_cost = as_core_direct_cost(result, key="batch-42")
    assert direct_cost.key == "batch-42"
    assert direct_cost.amount == Decimal("50.00")


def test_snapshot_is_exact_and_does_not_claim_inventory_or_tax_policy() -> None:
    result = calculate_manufacturing_batch(
        output_unit="piece",
        theoretical_output_quantity=Decimal("3"),
        good_output_quantity=Decimal("2"),
        materials=(MaterialUsage("material", Decimal("1"), Decimal("10.00"), "kg"),),
        conversion_costs=(),
    )
    snapshot = build_manufacturing_snapshot(result)

    assert snapshot["unit_cost"] == str(Decimal("10.00") / Decimal("2"))
    assert snapshot["inventory_valuation_policy_applied"] is False
    assert snapshot["tax_policy_applied"] is False
