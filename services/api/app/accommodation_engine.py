"""Accommodation room-night management economics.

The engine keeps capacity, occupancy, channel economics, and operating costs
explicit. It does not infer channel fee schedules, accommodation tax, VAT,
occupancy forecasts, or legal accounting policy.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.costing_engine import CostLine

ENGINE_VERSION = "accommodation-costing-v1"
ZERO = Decimal("0")
ONE = Decimal("1")

ACCOMMODATION_COST_CATEGORIES = frozenset(
    {
        "housekeeping",
        "laundry",
        "amenity",
        "breakfast",
        "energy",
        "water",
        "maintenance",
        "personnel",
        "software",
        "marketing",
        "other",
    }
)
COST_SCOPES = frozenset({"occupied_variable", "period_fixed"})


class AccommodationInputError(ValueError):
    """Raised when accommodation inputs violate room-night reconciliation."""


def _require_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise AccommodationInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise AccommodationInputError(f"{field} must be finite")
    return value


def _require_non_negative(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value < ZERO:
        raise AccommodationInputError(f"{field} must be non-negative")
    return decimal_value


def _require_rate(value: object, *, field: str) -> Decimal:
    decimal_value = _require_non_negative(value, field=field)
    if decimal_value >= ONE:
        raise AccommodationInputError(f"{field} must be less than 1")
    return decimal_value


def _require_key(value: str, *, field: str) -> None:
    if not value.strip():
        raise AccommodationInputError(f"{field} must not be blank")


def _require_positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AccommodationInputError(f"{field} must be a positive integer")
    return value


def _require_non_negative_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AccommodationInputError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class AccommodationCapacity:
    """Available room-night capacity and actual occupied room-nights."""

    available_rooms_per_night: int
    nights: int
    occupied_room_nights: int

    def __post_init__(self) -> None:
        rooms = _require_positive_int(
            self.available_rooms_per_night,
            field="capacity.available_rooms_per_night",
        )
        nights = _require_positive_int(self.nights, field="capacity.nights")
        occupied = _require_non_negative_int(
            self.occupied_room_nights,
            field="capacity.occupied_room_nights",
        )
        if occupied > rooms * nights:
            raise AccommodationInputError(
                "occupied_room_nights cannot exceed available_room_nights"
            )

    @property
    def available_room_nights(self) -> int:
        return self.available_rooms_per_night * self.nights

    @property
    def occupancy_ratio(self) -> Decimal:
        return Decimal(self.occupied_room_nights) / Decimal(self.available_room_nights)


@dataclass(frozen=True)
class AccommodationChannelSale:
    """Room-night sales and explicit channel charges for one sales channel."""

    key: str
    room_nights: int
    gross_room_revenue: Decimal
    revenue_reduction_amount: Decimal = ZERO
    commission_base_amount: Decimal = ZERO
    commission_rate: Decimal = ZERO
    fixed_channel_fee: Decimal = ZERO

    def __post_init__(self) -> None:
        _require_key(self.key, field="channel_sale.key")
        _require_positive_int(self.room_nights, field=f"channel_sale[{self.key}].room_nights")
        gross = _require_non_negative(
            self.gross_room_revenue,
            field=f"channel_sale[{self.key}].gross_room_revenue",
        )
        reduction = _require_non_negative(
            self.revenue_reduction_amount,
            field=f"channel_sale[{self.key}].revenue_reduction_amount",
        )
        if reduction > gross:
            raise AccommodationInputError(
                f"channel_sale[{self.key}] revenue reduction cannot exceed gross revenue"
            )
        _require_non_negative(
            self.commission_base_amount,
            field=f"channel_sale[{self.key}].commission_base_amount",
        )
        _require_rate(
            self.commission_rate,
            field=f"channel_sale[{self.key}].commission_rate",
        )
        _require_non_negative(
            self.fixed_channel_fee,
            field=f"channel_sale[{self.key}].fixed_channel_fee",
        )

    @property
    def net_room_revenue_before_channel_fee(self) -> Decimal:
        return self.gross_room_revenue - self.revenue_reduction_amount

    @property
    def percentage_channel_fee(self) -> Decimal:
        return self.commission_base_amount * self.commission_rate

    @property
    def total_channel_fee(self) -> Decimal:
        return self.percentage_channel_fee + self.fixed_channel_fee

    @property
    def net_room_revenue_after_channel_fee(self) -> Decimal:
        return self.net_room_revenue_before_channel_fee - self.total_channel_fee


@dataclass(frozen=True)
class AccommodationCost:
    """Explicit accommodation period cost with management scope semantics."""

    key: str
    category: str
    scope: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="accommodation_cost.key")
        if self.category not in ACCOMMODATION_COST_CATEGORIES:
            raise AccommodationInputError(
                f"unsupported accommodation cost category: {self.category}"
            )
        if self.scope not in COST_SCOPES:
            raise AccommodationInputError(f"unsupported accommodation cost scope: {self.scope}")
        _require_non_negative(self.amount, field=f"accommodation_cost[{self.key}].amount")


@dataclass(frozen=True)
class AccommodationResult:
    """Room-night economics before accommodation-tax/VAT/legal accounting rules."""

    available_room_nights: int
    occupied_room_nights: int
    occupancy_ratio: Decimal
    gross_room_revenue: Decimal
    revenue_reduction_amount: Decimal
    net_room_revenue_before_channel_fee: Decimal
    percentage_channel_fee: Decimal
    fixed_channel_fee: Decimal
    total_channel_fee: Decimal
    net_room_revenue_after_channel_fee: Decimal
    channel_revenue_totals: tuple[tuple[str, Decimal], ...]
    occupied_variable_cost: Decimal
    period_fixed_cost: Decimal
    total_operating_cost: Decimal
    cost_category_totals: tuple[tuple[str, Decimal], ...]
    cost_per_occupied_room_night: Decimal | None
    cost_per_available_room_night: Decimal
    net_revenue_per_occupied_room_night: Decimal | None
    net_revenue_per_available_room_night: Decimal
    accommodation_contribution: Decimal
    contribution_margin_ratio: Decimal | None


def _ensure_unique_keys(
    items: Iterable[AccommodationChannelSale | AccommodationCost],
) -> None:
    seen: set[str] = set()
    for item in items:
        if item.key in seen:
            raise AccommodationInputError(f"duplicate accommodation line key: {item.key}")
        seen.add(item.key)


def _category_totals(costs: Sequence[AccommodationCost]) -> tuple[tuple[str, Decimal], ...]:
    totals: dict[str, Decimal] = {}
    for line in costs:
        totals[line.category] = totals.get(line.category, ZERO) + line.amount
    return tuple(sorted(totals.items()))


def _channel_revenue_totals(
    channel_sales: Sequence[AccommodationChannelSale],
) -> tuple[tuple[str, Decimal], ...]:
    return tuple(
        sorted((line.key, line.net_room_revenue_after_channel_fee) for line in channel_sales)
    )


def calculate_accommodation_result(
    *,
    capacity: AccommodationCapacity,
    channel_sales: Sequence[AccommodationChannelSale],
    costs: Sequence[AccommodationCost],
) -> AccommodationResult:
    """Calculate room-night economics from explicit occupancy, channels, and costs."""

    _ensure_unique_keys((*channel_sales, *costs))
    sold_room_nights = sum(line.room_nights for line in channel_sales)
    if sold_room_nights != capacity.occupied_room_nights:
        raise AccommodationInputError("channel room_nights must equal occupied_room_nights")

    gross_room_revenue = sum((line.gross_room_revenue for line in channel_sales), ZERO)
    revenue_reduction = sum((line.revenue_reduction_amount for line in channel_sales), ZERO)
    net_before_channel = gross_room_revenue - revenue_reduction
    percentage_channel_fee = sum(
        (line.percentage_channel_fee for line in channel_sales),
        ZERO,
    )
    fixed_channel_fee = sum((line.fixed_channel_fee for line in channel_sales), ZERO)
    total_channel_fee = percentage_channel_fee + fixed_channel_fee
    net_after_channel = net_before_channel - total_channel_fee

    occupied_variable_cost = sum(
        (line.amount for line in costs if line.scope == "occupied_variable"),
        ZERO,
    )
    period_fixed_cost = sum(
        (line.amount for line in costs if line.scope == "period_fixed"),
        ZERO,
    )
    total_operating_cost = occupied_variable_cost + period_fixed_cost

    occupied = capacity.occupied_room_nights
    available = capacity.available_room_nights
    cost_per_occupied = total_operating_cost / Decimal(occupied) if occupied > 0 else None
    net_revenue_per_occupied = net_after_channel / Decimal(occupied) if occupied > 0 else None
    cost_per_available = total_operating_cost / Decimal(available)
    net_revenue_per_available = net_after_channel / Decimal(available)
    contribution = net_after_channel - total_operating_cost
    contribution_margin = contribution / net_after_channel if net_after_channel != ZERO else None

    return AccommodationResult(
        available_room_nights=available,
        occupied_room_nights=occupied,
        occupancy_ratio=capacity.occupancy_ratio,
        gross_room_revenue=gross_room_revenue,
        revenue_reduction_amount=revenue_reduction,
        net_room_revenue_before_channel_fee=net_before_channel,
        percentage_channel_fee=percentage_channel_fee,
        fixed_channel_fee=fixed_channel_fee,
        total_channel_fee=total_channel_fee,
        net_room_revenue_after_channel_fee=net_after_channel,
        channel_revenue_totals=_channel_revenue_totals(channel_sales),
        occupied_variable_cost=occupied_variable_cost,
        period_fixed_cost=period_fixed_cost,
        total_operating_cost=total_operating_cost,
        cost_category_totals=_category_totals(costs),
        cost_per_occupied_room_night=cost_per_occupied,
        cost_per_available_room_night=cost_per_available,
        net_revenue_per_occupied_room_night=net_revenue_per_occupied,
        net_revenue_per_available_room_night=net_revenue_per_available,
        accommodation_contribution=contribution,
        contribution_margin_ratio=contribution_margin,
    )


def as_core_direct_cost(
    result: AccommodationResult,
    *,
    key: str = "accommodation-period",
) -> CostLine:
    """Bridge accommodation operating cost into the sector-neutral costing core."""

    _require_key(key, field="core_cost_key")
    return CostLine(key=key, amount=result.total_operating_cost)


def build_accommodation_snapshot(result: AccommodationResult) -> dict[str, object]:
    """Serialize exact room economics without claiming tax/regulatory treatment."""

    return {
        "engine_version": ENGINE_VERSION,
        "available_room_nights": result.available_room_nights,
        "occupied_room_nights": result.occupied_room_nights,
        "occupancy_ratio": str(result.occupancy_ratio),
        "gross_room_revenue": str(result.gross_room_revenue),
        "revenue_reduction_amount": str(result.revenue_reduction_amount),
        "net_room_revenue_before_channel_fee": str(result.net_room_revenue_before_channel_fee),
        "percentage_channel_fee": str(result.percentage_channel_fee),
        "fixed_channel_fee": str(result.fixed_channel_fee),
        "total_channel_fee": str(result.total_channel_fee),
        "net_room_revenue_after_channel_fee": str(result.net_room_revenue_after_channel_fee),
        "channel_revenue_totals": {
            channel: str(amount) for channel, amount in result.channel_revenue_totals
        },
        "occupied_variable_cost": str(result.occupied_variable_cost),
        "period_fixed_cost": str(result.period_fixed_cost),
        "total_operating_cost": str(result.total_operating_cost),
        "cost_category_totals": {
            category: str(amount) for category, amount in result.cost_category_totals
        },
        "cost_per_occupied_room_night": (
            str(result.cost_per_occupied_room_night)
            if result.cost_per_occupied_room_night is not None
            else None
        ),
        "cost_per_available_room_night": str(result.cost_per_available_room_night),
        "net_revenue_per_occupied_room_night": (
            str(result.net_revenue_per_occupied_room_night)
            if result.net_revenue_per_occupied_room_night is not None
            else None
        ),
        "net_revenue_per_available_room_night": str(result.net_revenue_per_available_room_night),
        "accommodation_contribution": str(result.accommodation_contribution),
        "contribution_margin_ratio": (
            str(result.contribution_margin_ratio)
            if result.contribution_margin_ratio is not None
            else None
        ),
        "channel_fee_schedule_inferred": False,
        "occupancy_forecast_inferred": False,
        "accommodation_tax_policy_applied": False,
        "vat_treatment_applied": False,
        "inventory_accounting_policy_applied": False,
    }
