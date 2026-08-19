"""Regression tests for transportation trip-cost economics."""

from decimal import Decimal

import pytest

from app.transportation_engine import (
    CargoLoad,
    DistanceConsumption,
    PersonnelTripCost,
    RouteTripCost,
    TransportationInputError,
    TripDistance,
    VehicleAllocatedCost,
    as_core_direct_cost,
    build_transportation_snapshot,
    calculate_transportation_trip,
)


def test_trip_cost_calculates_loaded_empty_fuel_adblue_and_allocations() -> None:
    result = calculate_transportation_trip(
        distance=TripDistance(loaded_km=Decimal("500"), empty_km=Decimal("100")),
        distance_consumptions=(
            DistanceConsumption(
                "diesel",
                "fuel",
                quantity_per_100_km=Decimal("30"),
                unit_price=Decimal("50.00"),
                unit="liter",
            ),
            DistanceConsumption(
                "adblue",
                "adblue",
                quantity_per_100_km=Decimal("1.5"),
                unit_price=Decimal("20.00"),
                unit="liter",
            ),
        ),
        route_costs=(
            RouteTripCost("toll", "toll", Decimal("1200.00")),
            RouteTripCost("ferry", "ferry", Decimal("500.00")),
        ),
        personnel_costs=(
            PersonnelTripCost("driver", "driver_labor", Decimal("2000.00")),
            PersonnelTripCost("per-diem", "per_diem", Decimal("500.00")),
        ),
        vehicle_costs=(
            VehicleAllocatedCost("maintenance", "maintenance", Decimal("600.00")),
            VehicleAllocatedCost("tyre", "tyre", Decimal("300.00")),
            VehicleAllocatedCost("depreciation", "depreciation", Decimal("800.00")),
        ),
        cargo=CargoLoad(
            quantity=Decimal("20"),
            unit="ton",
            capacity_quantity=Decimal("25"),
        ),
    )

    assert result.total_km == Decimal("600")
    assert result.consumption_cost == Decimal("9180.000")
    assert result.route_cost == Decimal("1700.00")
    assert result.personnel_cost == Decimal("2500.00")
    assert result.vehicle_allocated_cost == Decimal("1700.00")
    assert result.total_trip_cost == Decimal("15080.000")
    assert result.cost_per_total_km == Decimal("15080.000") / Decimal("600")
    assert result.cost_per_loaded_km == Decimal("15080.000") / Decimal("500")
    assert result.cost_per_cargo_unit == Decimal("15080.000") / Decimal("20")
    assert result.capacity_utilization_ratio == Decimal("0.8")
    assert result.ton_km == Decimal("10000")
    assert result.cost_per_ton_km == Decimal("15080.000") / Decimal("10000")


def test_distance_consumption_uses_total_loaded_plus_empty_kilometres() -> None:
    distance = TripDistance(loaded_km=Decimal("80"), empty_km=Decimal("20"))
    fuel = DistanceConsumption(
        "fuel",
        "fuel",
        quantity_per_100_km=Decimal("25"),
        unit_price=Decimal("40.00"),
        unit="liter",
    )

    assert fuel.quantity_for_distance(distance.total_km) == Decimal("25")
    assert fuel.cost_for_distance(distance.total_km) == Decimal("1000.00")


def test_zero_loaded_km_has_no_fabricated_loaded_km_cost_or_ton_km_rate() -> None:
    result = calculate_transportation_trip(
        distance=TripDistance(loaded_km=Decimal("0"), empty_km=Decimal("50")),
        distance_consumptions=(),
        route_costs=(RouteTripCost("parking", "parking", Decimal("100.00")),),
        personnel_costs=(),
        vehicle_costs=(),
        cargo=CargoLoad(quantity=Decimal("10"), unit="ton"),
    )

    assert result.cost_per_loaded_km is None
    assert result.ton_km == Decimal("0")
    assert result.cost_per_ton_km is None


def test_non_ton_cargo_does_not_create_ton_km_by_guessing_unit_conversion() -> None:
    result = calculate_transportation_trip(
        distance=TripDistance(loaded_km=Decimal("100"), empty_km=Decimal("0")),
        distance_consumptions=(),
        route_costs=(),
        personnel_costs=(),
        vehicle_costs=(VehicleAllocatedCost("vehicle", "maintenance", Decimal("500.00")),),
        cargo=CargoLoad(quantity=Decimal("12"), unit="pallet"),
    )

    assert result.cost_per_cargo_unit == Decimal("500.00") / Decimal("12")
    assert result.ton_km is None
    assert result.cost_per_ton_km is None


def test_cargo_cannot_exceed_capacity() -> None:
    with pytest.raises(TransportationInputError, match="cannot exceed capacity"):
        CargoLoad(
            quantity=Decimal("26"),
            unit="ton",
            capacity_quantity=Decimal("25"),
        )


def test_trip_total_distance_must_be_positive() -> None:
    with pytest.raises(TransportationInputError, match="total distance must be positive"):
        TripDistance(loaded_km=Decimal("0"), empty_km=Decimal("0"))


def test_runtime_rejects_binary_float_consumption_rate() -> None:
    with pytest.raises(TransportationInputError, match="must be Decimal"):
        DistanceConsumption(
            "fuel",
            "fuel",
            30.0,  # type: ignore[arg-type]
            Decimal("50.00"),
            "liter",
        )


def test_duplicate_key_across_transport_cost_groups_fails_closed() -> None:
    with pytest.raises(TransportationInputError, match="duplicate transportation line key"):
        calculate_transportation_trip(
            distance=TripDistance(loaded_km=Decimal("10"), empty_km=Decimal("0")),
            distance_consumptions=(
                DistanceConsumption(
                    "shared",
                    "fuel",
                    Decimal("10"),
                    Decimal("10.00"),
                    "liter",
                ),
            ),
            route_costs=(RouteTripCost("shared", "toll", Decimal("1.00")),),
            personnel_costs=(),
            vehicle_costs=(),
        )


def test_category_totals_are_deterministic() -> None:
    result = calculate_transportation_trip(
        distance=TripDistance(loaded_km=Decimal("100"), empty_km=Decimal("0")),
        distance_consumptions=(
            DistanceConsumption("f2", "fuel", Decimal("5"), Decimal("10.00"), "liter"),
            DistanceConsumption("a1", "adblue", Decimal("1"), Decimal("5.00"), "liter"),
            DistanceConsumption("f1", "fuel", Decimal("5"), Decimal("10.00"), "liter"),
        ),
        route_costs=(
            RouteTripCost("toll-2", "toll", Decimal("20.00")),
            RouteTripCost("bridge", "bridge", Decimal("30.00")),
            RouteTripCost("toll-1", "toll", Decimal("10.00")),
        ),
        personnel_costs=(),
        vehicle_costs=(),
    )

    assert result.consumption_category_costs == (
        ("adblue", Decimal("5.00")),
        ("fuel", Decimal("100.00")),
    )
    assert result.route_category_costs == (
        ("bridge", Decimal("30.00")),
        ("toll", Decimal("30.00")),
    )


def test_transportation_result_bridges_to_core_direct_cost() -> None:
    result = calculate_transportation_trip(
        distance=TripDistance(loaded_km=Decimal("10"), empty_km=Decimal("0")),
        distance_consumptions=(),
        route_costs=(RouteTripCost("toll", "toll", Decimal("50.00")),),
        personnel_costs=(),
        vehicle_costs=(),
    )
    cost_line = as_core_direct_cost(result, key="trip-42")

    assert cost_line.key == "trip-42"
    assert cost_line.amount == Decimal("50.00")


def test_snapshot_does_not_claim_external_prices_routes_or_policies() -> None:
    result = calculate_transportation_trip(
        distance=TripDistance(loaded_km=Decimal("10"), empty_km=Decimal("5")),
        distance_consumptions=(),
        route_costs=(),
        personnel_costs=(),
        vehicle_costs=(),
    )
    snapshot = build_transportation_snapshot(result)

    assert snapshot["route_distance_inferred"] is False
    assert snapshot["fuel_price_inferred"] is False
    assert snapshot["toll_schedule_inferred"] is False
    assert snapshot["payroll_policy_applied"] is False
    assert snapshot["depreciation_policy_applied"] is False
    assert snapshot["legal_driving_hours_policy_applied"] is False
