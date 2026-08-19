"""Transportation trip-cost primitives with explicit operational inputs.

The engine does not infer route distance, fuel prices, toll schedules, payroll,
depreciation, or legal driving-hour rules. Every operational input is supplied
explicitly by the caller and calculated with Decimal arithmetic.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.costing_engine import CostLine

ENGINE_VERSION = "transportation-costing-v1"
ZERO = Decimal("0")
HUNDRED = Decimal("100")

DISTANCE_CONSUMPTION_CATEGORIES = frozenset({"fuel", "adblue", "other"})
ROUTE_COST_CATEGORIES = frozenset(
    {"toll", "bridge", "ferry", "parking", "loading", "unloading", "other"}
)
PERSONNEL_COST_CATEGORIES = frozenset(
    {"driver_labor", "assistant_labor", "per_diem", "accommodation", "other"}
)
VEHICLE_COST_CATEGORIES = frozenset(
    {"maintenance", "tyre", "insurance", "depreciation", "financing", "other"}
)


class TransportationInputError(ValueError):
    """Raised when transportation inputs violate explicit trip-cost contracts."""


def _require_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TransportationInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise TransportationInputError(f"{field} must be finite")
    return value


def _require_non_negative(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value < ZERO:
        raise TransportationInputError(f"{field} must be non-negative")
    return decimal_value


def _require_positive(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value <= ZERO:
        raise TransportationInputError(f"{field} must be positive")
    return decimal_value


def _require_key(value: str, *, field: str) -> None:
    if not value.strip():
        raise TransportationInputError(f"{field} must not be blank")


@dataclass(frozen=True)
class TripDistance:
    """Caller-supplied loaded and empty road distance in kilometres."""

    loaded_km: Decimal
    empty_km: Decimal

    def __post_init__(self) -> None:
        _require_non_negative(self.loaded_km, field="distance.loaded_km")
        _require_non_negative(self.empty_km, field="distance.empty_km")
        if self.total_km <= ZERO:
            raise TransportationInputError("trip total distance must be positive")

    @property
    def total_km(self) -> Decimal:
        return self.loaded_km + self.empty_km


@dataclass(frozen=True)
class DistanceConsumption:
    """Fuel/AdBlue/other consumption priced per 100 kilometres."""

    key: str
    category: str
    quantity_per_100_km: Decimal
    unit_price: Decimal
    unit: str

    def __post_init__(self) -> None:
        _require_key(self.key, field="distance_consumption.key")
        _require_key(self.unit, field=f"distance_consumption[{self.key}].unit")
        if self.category not in DISTANCE_CONSUMPTION_CATEGORIES:
            raise TransportationInputError(
                f"unsupported distance consumption category: {self.category}"
            )
        _require_non_negative(
            self.quantity_per_100_km,
            field=f"distance_consumption[{self.key}].quantity_per_100_km",
        )
        _require_non_negative(
            self.unit_price,
            field=f"distance_consumption[{self.key}].unit_price",
        )

    def quantity_for_distance(self, total_km: Decimal) -> Decimal:
        return total_km * self.quantity_per_100_km / HUNDRED

    def cost_for_distance(self, total_km: Decimal) -> Decimal:
        return self.quantity_for_distance(total_km) * self.unit_price


@dataclass(frozen=True)
class RouteTripCost:
    """Explicit toll/bridge/ferry/loading or other route-specific trip charge."""

    key: str
    category: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="route_cost.key")
        if self.category not in ROUTE_COST_CATEGORIES:
            raise TransportationInputError(f"unsupported route cost category: {self.category}")
        _require_non_negative(self.amount, field=f"route_cost[{self.key}].amount")


@dataclass(frozen=True)
class PersonnelTripCost:
    """Explicit personnel amount allocated to the trip."""

    key: str
    category: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="personnel_cost.key")
        if self.category not in PERSONNEL_COST_CATEGORIES:
            raise TransportationInputError(f"unsupported personnel cost category: {self.category}")
        _require_non_negative(self.amount, field=f"personnel_cost[{self.key}].amount")


@dataclass(frozen=True)
class VehicleAllocatedCost:
    """Explicit vehicle cost allocated to the trip by an upstream policy."""

    key: str
    category: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="vehicle_cost.key")
        if self.category not in VEHICLE_COST_CATEGORIES:
            raise TransportationInputError(f"unsupported vehicle cost category: {self.category}")
        _require_non_negative(self.amount, field=f"vehicle_cost[{self.key}].amount")


@dataclass(frozen=True)
class CargoLoad:
    """Cargo quantity and optional capacity expressed in the same explicit unit."""

    quantity: Decimal
    unit: str
    capacity_quantity: Decimal | None = None

    def __post_init__(self) -> None:
        quantity = _require_positive(self.quantity, field="cargo.quantity")
        _require_key(self.unit, field="cargo.unit")
        if self.capacity_quantity is not None:
            capacity = _require_positive(self.capacity_quantity, field="cargo.capacity_quantity")
            if quantity > capacity:
                raise TransportationInputError("cargo quantity cannot exceed capacity quantity")


@dataclass(frozen=True)
class TransportationResult:
    """Trip management-cost result and safe operational unit economics."""

    loaded_km: Decimal
    empty_km: Decimal
    total_km: Decimal
    consumption_cost: Decimal
    consumption_category_costs: tuple[tuple[str, Decimal], ...]
    route_cost: Decimal
    route_category_costs: tuple[tuple[str, Decimal], ...]
    personnel_cost: Decimal
    personnel_category_costs: tuple[tuple[str, Decimal], ...]
    vehicle_allocated_cost: Decimal
    vehicle_category_costs: tuple[tuple[str, Decimal], ...]
    total_trip_cost: Decimal
    cost_per_total_km: Decimal
    cost_per_loaded_km: Decimal | None
    cargo_quantity: Decimal | None
    cargo_unit: str | None
    cost_per_cargo_unit: Decimal | None
    capacity_utilization_ratio: Decimal | None
    ton_km: Decimal | None
    cost_per_ton_km: Decimal | None


def _ensure_unique_keys(
    items: Iterable[DistanceConsumption | RouteTripCost | PersonnelTripCost | VehicleAllocatedCost],
) -> None:
    seen: set[str] = set()
    for item in items:
        if item.key in seen:
            raise TransportationInputError(f"duplicate transportation line key: {item.key}")
        seen.add(item.key)


def _category_totals(
    pairs: Iterable[tuple[str, Decimal]],
) -> tuple[tuple[str, Decimal], ...]:
    totals: dict[str, Decimal] = {}
    for category, amount in pairs:
        totals[category] = totals.get(category, ZERO) + amount
    return tuple(sorted(totals.items()))


def calculate_transportation_trip(
    *,
    distance: TripDistance,
    distance_consumptions: Sequence[DistanceConsumption],
    route_costs: Sequence[RouteTripCost],
    personnel_costs: Sequence[PersonnelTripCost],
    vehicle_costs: Sequence[VehicleAllocatedCost],
    cargo: CargoLoad | None = None,
) -> TransportationResult:
    """Calculate one trip from explicit distance, consumption and allocated costs."""

    _ensure_unique_keys((*distance_consumptions, *route_costs, *personnel_costs, *vehicle_costs))

    consumption_category_costs = _category_totals(
        (line.category, line.cost_for_distance(distance.total_km)) for line in distance_consumptions
    )
    route_category_costs = _category_totals((line.category, line.amount) for line in route_costs)
    personnel_category_costs = _category_totals(
        (line.category, line.amount) for line in personnel_costs
    )
    vehicle_category_costs = _category_totals(
        (line.category, line.amount) for line in vehicle_costs
    )

    consumption_cost = sum((amount for _, amount in consumption_category_costs), ZERO)
    route_cost = sum((amount for _, amount in route_category_costs), ZERO)
    personnel_cost = sum((amount for _, amount in personnel_category_costs), ZERO)
    vehicle_allocated_cost = sum((amount for _, amount in vehicle_category_costs), ZERO)
    total_trip_cost = consumption_cost + route_cost + personnel_cost + vehicle_allocated_cost

    cost_per_total_km = total_trip_cost / distance.total_km
    cost_per_loaded_km = total_trip_cost / distance.loaded_km if distance.loaded_km > ZERO else None

    cargo_quantity: Decimal | None = None
    cargo_unit: str | None = None
    cost_per_cargo_unit: Decimal | None = None
    capacity_utilization_ratio: Decimal | None = None
    ton_km: Decimal | None = None
    cost_per_ton_km: Decimal | None = None

    if cargo is not None:
        cargo_quantity = cargo.quantity
        cargo_unit = cargo.unit
        cost_per_cargo_unit = total_trip_cost / cargo.quantity
        if cargo.capacity_quantity is not None:
            capacity_utilization_ratio = cargo.quantity / cargo.capacity_quantity
        if cargo.unit == "ton":
            ton_km = cargo.quantity * distance.loaded_km
            if ton_km > ZERO:
                cost_per_ton_km = total_trip_cost / ton_km

    return TransportationResult(
        loaded_km=distance.loaded_km,
        empty_km=distance.empty_km,
        total_km=distance.total_km,
        consumption_cost=consumption_cost,
        consumption_category_costs=consumption_category_costs,
        route_cost=route_cost,
        route_category_costs=route_category_costs,
        personnel_cost=personnel_cost,
        personnel_category_costs=personnel_category_costs,
        vehicle_allocated_cost=vehicle_allocated_cost,
        vehicle_category_costs=vehicle_category_costs,
        total_trip_cost=total_trip_cost,
        cost_per_total_km=cost_per_total_km,
        cost_per_loaded_km=cost_per_loaded_km,
        cargo_quantity=cargo_quantity,
        cargo_unit=cargo_unit,
        cost_per_cargo_unit=cost_per_cargo_unit,
        capacity_utilization_ratio=capacity_utilization_ratio,
        ton_km=ton_km,
        cost_per_ton_km=cost_per_ton_km,
    )


def as_core_direct_cost(result: TransportationResult, *, key: str = "transport-trip") -> CostLine:
    """Bridge trip cost into the sector-neutral costing engine."""

    _require_key(key, field="core_cost_key")
    return CostLine(key=key, amount=result.total_trip_cost)


def build_transportation_snapshot(result: TransportationResult) -> dict[str, object]:
    """Serialize exact trip economics without claiming inferred external policies."""

    return {
        "engine_version": ENGINE_VERSION,
        "loaded_km": str(result.loaded_km),
        "empty_km": str(result.empty_km),
        "total_km": str(result.total_km),
        "consumption_cost": str(result.consumption_cost),
        "consumption_category_costs": {
            category: str(amount) for category, amount in result.consumption_category_costs
        },
        "route_cost": str(result.route_cost),
        "route_category_costs": {
            category: str(amount) for category, amount in result.route_category_costs
        },
        "personnel_cost": str(result.personnel_cost),
        "personnel_category_costs": {
            category: str(amount) for category, amount in result.personnel_category_costs
        },
        "vehicle_allocated_cost": str(result.vehicle_allocated_cost),
        "vehicle_category_costs": {
            category: str(amount) for category, amount in result.vehicle_category_costs
        },
        "total_trip_cost": str(result.total_trip_cost),
        "cost_per_total_km": str(result.cost_per_total_km),
        "cost_per_loaded_km": (
            str(result.cost_per_loaded_km) if result.cost_per_loaded_km is not None else None
        ),
        "cargo_quantity": str(result.cargo_quantity) if result.cargo_quantity is not None else None,
        "cargo_unit": result.cargo_unit,
        "cost_per_cargo_unit": (
            str(result.cost_per_cargo_unit) if result.cost_per_cargo_unit is not None else None
        ),
        "capacity_utilization_ratio": (
            str(result.capacity_utilization_ratio)
            if result.capacity_utilization_ratio is not None
            else None
        ),
        "ton_km": str(result.ton_km) if result.ton_km is not None else None,
        "cost_per_ton_km": (
            str(result.cost_per_ton_km) if result.cost_per_ton_km is not None else None
        ),
        "route_distance_inferred": False,
        "fuel_price_inferred": False,
        "toll_schedule_inferred": False,
        "payroll_policy_applied": False,
        "depreciation_policy_applied": False,
        "legal_driving_hours_policy_applied": False,
    }
