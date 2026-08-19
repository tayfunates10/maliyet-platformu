"""Regression tests for the textile manufacturing adapter."""

from decimal import Decimal

import pytest

from app.manufacturing_engine import RecoveryCredit
from app.textile_manufacturing import (
    TextileManufacturingInputError,
    TextileMaterial,
    TextileProcessCost,
    build_textile_snapshot,
    calculate_textile_batch,
)


def test_textile_batch_preserves_native_material_units_and_piece_yield() -> None:
    result = calculate_textile_batch(
        theoretical_piece_count=1000,
        cutting_reject_count=30,
        quality_reject_count=20,
        ordered_piece_count=900,
        materials=(
            TextileMaterial("shell", "fabric", Decimal("120"), Decimal("50.00"), "m"),
            TextileMaterial("lining", "lining", Decimal("50"), Decimal("20.00"), "m"),
            TextileMaterial("zipper", "accessory", Decimal("950"), Decimal("3.00"), "piece"),
        ),
        process_costs=(
            TextileProcessCost("cut", "cutting", "machine", Decimal("1200.00")),
            TextileProcessCost("sew", "sewing", "labor", Decimal("3000.00")),
            TextileProcessCost(
                "fason",
                "finishing",
                "subcontracting",
                Decimal("500.00"),
            ),
            TextileProcessCost("qc", "quality", "quality", Decimal("250.00")),
        ),
        recovery_credits=(RecoveryCredit("fabric-scrap", Decimal("300.00")),),
    )

    assert result.good_piece_count == 950
    assert result.surplus_good_piece_count == 50
    assert result.manufacturing.yield_ratio == Decimal("0.95")
    assert result.manufacturing.material_cost == Decimal("9850.00")
    assert result.manufacturing.conversion_cost == Decimal("4950.00")
    assert result.manufacturing.gross_batch_cost == Decimal("14800.00")
    assert result.manufacturing.net_batch_cost == Decimal("14500.00")
    assert result.finished_piece_unit_cost == Decimal("14500.00") / Decimal("950")
    assert result.management_order_cost == result.finished_piece_unit_cost * Decimal("900")


def test_material_category_totals_do_not_mix_physical_units() -> None:
    result = calculate_textile_batch(
        theoretical_piece_count=10,
        cutting_reject_count=0,
        quality_reject_count=0,
        ordered_piece_count=10,
        materials=(
            TextileMaterial("fabric", "fabric", Decimal("5"), Decimal("10.00"), "m"),
            TextileMaterial("yarn", "yarn", Decimal("2"), Decimal("20.00"), "kg"),
            TextileMaterial("button", "accessory", Decimal("40"), Decimal("0.25"), "piece"),
        ),
        process_costs=(),
    )

    assert result.material_category_costs == (
        ("accessory", Decimal("10.00")),
        ("fabric", Decimal("50.00")),
        ("yarn", Decimal("40.00")),
    )
    assert result.manufacturing.material_cost == Decimal("100.00")


def test_process_stage_totals_preserve_stage_semantics() -> None:
    result = calculate_textile_batch(
        theoretical_piece_count=10,
        cutting_reject_count=0,
        quality_reject_count=0,
        ordered_piece_count=10,
        materials=(),
        process_costs=(
            TextileProcessCost("cut-a", "cutting", "labor", Decimal("20.00")),
            TextileProcessCost("cut-b", "cutting", "machine", Decimal("30.00")),
            TextileProcessCost("sew", "sewing", "labor", Decimal("40.00")),
        ),
    )

    assert result.process_stage_costs == (
        ("cutting", Decimal("50.00")),
        ("sewing", Decimal("40.00")),
    )
    assert result.manufacturing.conversion_cost == Decimal("90.00")


def test_order_cannot_exceed_good_output() -> None:
    with pytest.raises(TextileManufacturingInputError, match="cannot exceed good_piece_count"):
        calculate_textile_batch(
            theoretical_piece_count=100,
            cutting_reject_count=10,
            quality_reject_count=0,
            ordered_piece_count=91,
            materials=(),
            process_costs=(),
        )


def test_rejects_cannot_consume_whole_output() -> None:
    with pytest.raises(TextileManufacturingInputError, match="leave positive good output"):
        calculate_textile_batch(
            theoretical_piece_count=100,
            cutting_reject_count=80,
            quality_reject_count=20,
            ordered_piece_count=1,
            materials=(),
            process_costs=(),
        )


def test_runtime_rejects_binary_float_material_quantity() -> None:
    with pytest.raises(TextileManufacturingInputError, match="must be Decimal"):
        TextileMaterial(
            "fabric",
            "fabric",
            1.5,  # type: ignore[arg-type]
            Decimal("10.00"),
            "m",
        )


def test_duplicate_key_across_textile_inputs_fails_closed() -> None:
    with pytest.raises(TextileManufacturingInputError, match="duplicate textile line key"):
        calculate_textile_batch(
            theoretical_piece_count=10,
            cutting_reject_count=0,
            quality_reject_count=0,
            ordered_piece_count=10,
            materials=(TextileMaterial("shared", "fabric", Decimal("1"), Decimal("1.00"), "m"),),
            process_costs=(TextileProcessCost("shared", "cutting", "labor", Decimal("1.00")),),
        )


def test_invalid_process_cost_category_fails_closed() -> None:
    with pytest.raises(TextileManufacturingInputError, match="unsupported textile cost category"):
        TextileProcessCost("bad", "cutting", "invented", Decimal("1.00"))


def test_snapshot_marks_management_allocation_and_unapplied_legal_policies() -> None:
    result = calculate_textile_batch(
        theoretical_piece_count=10,
        cutting_reject_count=0,
        quality_reject_count=0,
        ordered_piece_count=8,
        materials=(),
        process_costs=(),
    )
    snapshot = build_textile_snapshot(result)

    assert snapshot["order_cost_is_management_allocation"] is True
    assert snapshot["inventory_valuation_policy_applied"] is False
    assert snapshot["tax_waste_policy_applied"] is False
