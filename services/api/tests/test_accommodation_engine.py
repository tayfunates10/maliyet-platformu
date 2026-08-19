"""Regression tests for accommodation room-night management economics."""

from decimal import Decimal

import pytest

from app.accommodation_engine import (
    AccommodationCapacity,
    AccommodationChannelSale,
    AccommodationCost,
    AccommodationInputError,
    as_core_direct_cost,
    build_accommodation_snapshot,
    calculate_accommodation_result,
)


def test_accommodation_reconciles_capacity_channels_costs_and_contribution() -> None:
    result = calculate_accommodation_result(
        capacity=AccommodationCapacity(
            available_rooms_per_night=10,
            nights=30,
            occupied_room_nights=180,
        ),
        channel_sales=(
            AccommodationChannelSale(
                "direct",
                room_nights=100,
                gross_room_revenue=Decimal("100000.00"),
                revenue_reduction_amount=Decimal("5000.00"),
            ),
            AccommodationChannelSale(
                "ota",
                room_nights=80,
                gross_room_revenue=Decimal("96000.00"),
                revenue_reduction_amount=Decimal("4000.00"),
                commission_base_amount=Decimal("92000.00"),
                commission_rate=Decimal("0.15"),
                fixed_channel_fee=Decimal("1000.00"),
            ),
        ),
        costs=(
            AccommodationCost(
                "housekeeping",
                "housekeeping",
                "occupied_variable",
                Decimal("18000.00"),
            ),
            AccommodationCost("laundry", "laundry", "occupied_variable", Decimal("9000.00")),
            AccommodationCost("amenity", "amenity", "occupied_variable", Decimal("4500.00")),
            AccommodationCost("breakfast", "breakfast", "occupied_variable", Decimal("18000.00")),
            AccommodationCost("energy", "energy", "period_fixed", Decimal("20000.00")),
            AccommodationCost("water", "water", "period_fixed", Decimal("8000.00")),
            AccommodationCost("staff", "personnel", "period_fixed", Decimal("40000.00")),
            AccommodationCost("maintenance", "maintenance", "period_fixed", Decimal("10000.00")),
            AccommodationCost("software", "software", "period_fixed", Decimal("2000.00")),
        ),
    )

    assert result.available_room_nights == 300
    assert result.occupied_room_nights == 180
    assert result.occupancy_ratio == Decimal("0.6")
    assert result.gross_room_revenue == Decimal("196000.00")
    assert result.revenue_reduction_amount == Decimal("9000.00")
    assert result.net_room_revenue_before_channel_fee == Decimal("187000.00")
    assert result.percentage_channel_fee == Decimal("13800.0000")
    assert result.fixed_channel_fee == Decimal("1000.00")
    assert result.total_channel_fee == Decimal("14800.0000")
    assert result.net_room_revenue_after_channel_fee == Decimal("172200.0000")
    assert result.occupied_variable_cost == Decimal("49500.00")
    assert result.period_fixed_cost == Decimal("80000.00")
    assert result.total_operating_cost == Decimal("129500.00")
    assert result.cost_per_occupied_room_night == Decimal("129500.00") / Decimal("180")
    assert result.cost_per_available_room_night == Decimal("129500.00") / Decimal("300")
    assert result.net_revenue_per_occupied_room_night == Decimal("172200.0000") / Decimal("180")
    assert result.net_revenue_per_available_room_night == Decimal("172200.0000") / Decimal("300")
    assert result.accommodation_contribution == Decimal("42700.0000")
    assert result.contribution_margin_ratio == Decimal("42700.0000") / Decimal("172200.0000")


def test_channel_commission_uses_explicit_base_not_inferred_revenue() -> None:
    sale = AccommodationChannelSale(
        "ota",
        room_nights=1,
        gross_room_revenue=Decimal("1000.00"),
        commission_base_amount=Decimal("500.00"),
        commission_rate=Decimal("0.10"),
    )

    assert sale.percentage_channel_fee == Decimal("50.0000")
    assert sale.net_room_revenue_after_channel_fee == Decimal("950.0000")


def test_channel_room_nights_must_equal_occupied_room_nights() -> None:
    with pytest.raises(AccommodationInputError, match="must equal occupied_room_nights"):
        calculate_accommodation_result(
            capacity=AccommodationCapacity(10, 1, 5),
            channel_sales=(AccommodationChannelSale("direct", 4, Decimal("400.00")),),
            costs=(),
        )


def test_occupied_room_nights_cannot_exceed_capacity() -> None:
    with pytest.raises(AccommodationInputError, match="cannot exceed available_room_nights"):
        AccommodationCapacity(available_rooms_per_night=10, nights=2, occupied_room_nights=21)


def test_zero_occupancy_has_no_fabricated_per_occupied_room_metrics() -> None:
    result = calculate_accommodation_result(
        capacity=AccommodationCapacity(
            available_rooms_per_night=10,
            nights=10,
            occupied_room_nights=0,
        ),
        channel_sales=(),
        costs=(AccommodationCost("staff", "personnel", "period_fixed", Decimal("10000.00")),),
    )

    assert result.occupancy_ratio == Decimal("0")
    assert result.cost_per_occupied_room_night is None
    assert result.net_revenue_per_occupied_room_night is None
    assert result.cost_per_available_room_night == Decimal("100.00")
    assert result.accommodation_contribution == Decimal("-10000.00")
    assert result.contribution_margin_ratio is None


def test_revenue_reduction_cannot_exceed_gross_room_revenue() -> None:
    with pytest.raises(AccommodationInputError, match="cannot exceed gross revenue"):
        AccommodationChannelSale(
            "bad",
            room_nights=1,
            gross_room_revenue=Decimal("100.00"),
            revenue_reduction_amount=Decimal("100.01"),
        )


def test_commission_rate_must_be_less_than_one() -> None:
    with pytest.raises(AccommodationInputError, match="less than 1"):
        AccommodationChannelSale(
            "bad-rate",
            room_nights=1,
            gross_room_revenue=Decimal("100.00"),
            commission_rate=Decimal("1.00"),
        )


def test_runtime_rejects_binary_float_cost() -> None:
    with pytest.raises(AccommodationInputError, match="must be Decimal"):
        AccommodationCost(
            "float-cost",
            "energy",
            "period_fixed",
            1.5,  # type: ignore[arg-type]
        )


def test_duplicate_key_across_channel_and_cost_fails_closed() -> None:
    with pytest.raises(AccommodationInputError, match="duplicate accommodation line key"):
        calculate_accommodation_result(
            capacity=AccommodationCapacity(1, 1, 1),
            channel_sales=(AccommodationChannelSale("shared", 1, Decimal("100.00")),),
            costs=(AccommodationCost("shared", "energy", "period_fixed", Decimal("10.00")),),
        )


def test_cost_category_and_channel_totals_are_deterministic() -> None:
    result = calculate_accommodation_result(
        capacity=AccommodationCapacity(2, 1, 2),
        channel_sales=(
            AccommodationChannelSale("ota-b", 1, Decimal("100.00")),
            AccommodationChannelSale("direct-a", 1, Decimal("100.00")),
        ),
        costs=(
            AccommodationCost("energy-b", "energy", "period_fixed", Decimal("20.00")),
            AccommodationCost("laundry", "laundry", "occupied_variable", Decimal("5.00")),
            AccommodationCost("energy-a", "energy", "period_fixed", Decimal("10.00")),
        ),
    )

    assert result.channel_revenue_totals == (
        ("direct-a", Decimal("100.00")),
        ("ota-b", Decimal("100.00")),
    )
    assert result.cost_category_totals == (
        ("energy", Decimal("30.00")),
        ("laundry", Decimal("5.00")),
    )


def test_accommodation_cost_bridges_to_core_direct_cost() -> None:
    result = calculate_accommodation_result(
        capacity=AccommodationCapacity(1, 1, 0),
        channel_sales=(),
        costs=(AccommodationCost("staff", "personnel", "period_fixed", Decimal("50.00")),),
    )
    line = as_core_direct_cost(result, key="hotel-period")

    assert line.key == "hotel-period"
    assert line.amount == Decimal("50.00")


def test_snapshot_does_not_claim_tax_fee_schedule_or_forecast_policies() -> None:
    result = calculate_accommodation_result(
        capacity=AccommodationCapacity(1, 1, 0),
        channel_sales=(),
        costs=(),
    )
    snapshot = build_accommodation_snapshot(result)

    assert snapshot["channel_fee_schedule_inferred"] is False
    assert snapshot["occupancy_forecast_inferred"] is False
    assert snapshot["accommodation_tax_policy_applied"] is False
    assert snapshot["vat_treatment_applied"] is False
    assert snapshot["inventory_accounting_policy_applied"] is False
