"""Regression tests for the basic-metals manufacturing adapter."""

from decimal import Decimal

import pytest

from app.basic_metals_manufacturing import (
    BasicMetalsInputError,
    MetalEnergyUsage,
    MetalMaterial,
    MetalProcessCost,
    RecoveredScrap,
    build_basic_metals_snapshot,
    calculate_basic_metals_batch,
)


def test_basic_metals_batch_reconciles_losses_energy_and_scrap_credit() -> None:
    result = calculate_basic_metals_batch(
        output_unit="kg",
        theoretical_output_quantity=Decimal("10000"),
        melt_loss_quantity=Decimal("300"),
        slag_loss_quantity=Decimal("100"),
        quality_reject_quantity=Decimal("100"),
        materials=(
            MetalMaterial(
                "scrap-charge",
                "recycled_charge",
                Decimal("8000"),
                Decimal("5.00"),
                "kg",
            ),
            MetalMaterial("alloy", "alloy", Decimal("200"), Decimal("50.00"), "kg"),
        ),
        energy_usages=(
            MetalEnergyUsage("furnace", "melting", Decimal("2000"), Decimal("3.00"), "kWh"),
            MetalEnergyUsage("reheat", "reheating", Decimal("500"), Decimal("3.00"), "kWh"),
        ),
        process_costs=(
            MetalProcessCost("labor", "melting", "labor", Decimal("5000.00")),
            MetalProcessCost("qc", "quality", "quality", Decimal("1000.00")),
        ),
        recovered_scrap=(RecoveredScrap("return-scrap", Decimal("500"), Decimal("4.00"), "kg"),),
    )

    assert result.manufacturing.good_output_quantity == Decimal("9500")
    assert result.manufacturing.yield_ratio == Decimal("0.95")
    assert result.manufacturing.material_cost == Decimal("50000.00")
    assert result.manufacturing.conversion_cost == Decimal("13500.00")
    assert result.manufacturing.gross_batch_cost == Decimal("63500.00")
    assert result.recovered_scrap_credit == Decimal("2000.00")
    assert result.manufacturing.net_batch_cost == Decimal("61500.00")
    assert result.finished_output_unit_cost == Decimal("61500.00") / Decimal("9500")


def test_energy_stages_are_costed_without_physically_mixing_units() -> None:
    result = calculate_basic_metals_batch(
        output_unit="kg",
        theoretical_output_quantity=Decimal("100"),
        melt_loss_quantity=Decimal("0"),
        slag_loss_quantity=Decimal("0"),
        quality_reject_quantity=Decimal("0"),
        materials=(),
        energy_usages=(
            MetalEnergyUsage("electric", "melting", Decimal("10"), Decimal("2.00"), "kWh"),
            MetalEnergyUsage("gas", "reheating", Decimal("5"), Decimal("3.00"), "m3"),
        ),
        process_costs=(),
    )

    assert result.energy_stage_costs == (
        ("melting", Decimal("20.00")),
        ("reheating", Decimal("15.00")),
    )
    assert result.manufacturing.conversion_cost == Decimal("35.00")


def test_material_categories_are_reported_as_cost_not_fake_physical_total() -> None:
    result = calculate_basic_metals_batch(
        output_unit="kg",
        theoretical_output_quantity=Decimal("10"),
        melt_loss_quantity=Decimal("0"),
        slag_loss_quantity=Decimal("0"),
        quality_reject_quantity=Decimal("0"),
        materials=(
            MetalMaterial("metal", "primary_metal", Decimal("5"), Decimal("10.00"), "kg"),
            MetalMaterial("electrode", "electrode", Decimal("2"), Decimal("4.00"), "piece"),
        ),
        energy_usages=(),
        process_costs=(),
    )

    assert result.material_category_costs == (
        ("electrode", Decimal("8.00")),
        ("primary_metal", Decimal("50.00")),
    )
    assert result.manufacturing.material_cost == Decimal("58.00")


def test_losses_cannot_consume_all_engineering_output() -> None:
    with pytest.raises(BasicMetalsInputError, match="leave positive good output"):
        calculate_basic_metals_batch(
            output_unit="kg",
            theoretical_output_quantity=Decimal("100"),
            melt_loss_quantity=Decimal("70"),
            slag_loss_quantity=Decimal("20"),
            quality_reject_quantity=Decimal("10"),
            materials=(),
            energy_usages=(),
            process_costs=(),
        )


def test_runtime_rejects_binary_float_energy_quantity() -> None:
    with pytest.raises(BasicMetalsInputError, match="must be Decimal"):
        MetalEnergyUsage(
            "bad",
            "melting",
            1.5,  # type: ignore[arg-type]
            Decimal("2.00"),
            "kWh",
        )


def test_duplicate_key_across_basic_metals_inputs_fails_closed() -> None:
    with pytest.raises(BasicMetalsInputError, match="duplicate basic-metals line key"):
        calculate_basic_metals_batch(
            output_unit="kg",
            theoretical_output_quantity=Decimal("10"),
            melt_loss_quantity=Decimal("0"),
            slag_loss_quantity=Decimal("0"),
            quality_reject_quantity=Decimal("0"),
            materials=(
                MetalMaterial("shared", "primary_metal", Decimal("1"), Decimal("1.00"), "kg"),
            ),
            energy_usages=(
                MetalEnergyUsage("shared", "melting", Decimal("1"), Decimal("1.00"), "kWh"),
            ),
            process_costs=(),
        )


def test_invalid_process_cost_category_fails_closed() -> None:
    with pytest.raises(BasicMetalsInputError, match="unsupported metal cost category"):
        MetalProcessCost("bad", "melting", "invented", Decimal("1.00"))


def test_snapshot_refuses_to_infer_scrap_market_or_legal_waste_policy() -> None:
    result = calculate_basic_metals_batch(
        output_unit="kg",
        theoretical_output_quantity=Decimal("10"),
        melt_loss_quantity=Decimal("1"),
        slag_loss_quantity=Decimal("0"),
        quality_reject_quantity=Decimal("0"),
        materials=(),
        energy_usages=(),
        process_costs=(),
    )
    snapshot = build_basic_metals_snapshot(result)

    assert snapshot["scrap_market_value_inferred"] is False
    assert snapshot["inventory_valuation_policy_applied"] is False
    assert snapshot["tax_waste_policy_applied"] is False
