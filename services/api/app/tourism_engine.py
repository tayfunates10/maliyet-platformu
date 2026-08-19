"""Tourism package management economics with one explicit currency context.

The engine keeps participant capacity, channel revenue, variable/fixed package
components, and agency/channel charges explicit. It does not infer FX rates,
provider fee schedules, tourism taxes, VAT, or legal travel-package policy.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.costing_engine import CostLine

ENGINE_VERSION = "tourism-package-costing-v1"
ZERO = Decimal("0")
ONE = Decimal("1")

TOURISM_COMPONENT_CATEGORIES = frozenset(
    {
        "transportation",
        "accommodation",
        "guide",
        "transfer",
        "meal",
        "ticket",
        "activity",
        "insurance",
        "other",
    }
)
COMPONENT_SCOPES = frozenset({"per_participant", "fixed_package"})


class TourismInputError(ValueError):
    """Raised when tourism package inputs violate explicit package contracts."""


def _require_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TourismInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise TourismInputError(f"{field} must be finite")
    return value


def _require_non_negative(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value < ZERO:
        raise TourismInputError(f"{field} must be non-negative")
    return decimal_value


def _require_rate(value: object, *, field: str) -> Decimal:
    decimal_value = _require_non_negative(value, field=field)
    if decimal_value >= ONE:
        raise TourismInputError(f"{field} must be less than 1")
    return decimal_value


def _require_key(value: str, *, field: str) -> None:
    if not value.strip():
        raise TourismInputError(f"{field} must not be blank")


def _require_positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TourismInputError(f"{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class TourismPackagePlan:
    """Participant count and one pre-normalized currency context."""

    participant_count: int
    currency: str

    def __post_init__(self) -> None:
        _require_positive_int(self.participant_count, field="package.participant_count")
        _require_key(self.currency, field="package.currency")


@dataclass(frozen=True)
class TourismChannelSale:
    """Participant sales with explicit agency/channel fee base and rate."""

    key: str
    participant_count: int
    gross_revenue: Decimal
    revenue_reduction_amount: Decimal = ZERO
    commission_base_amount: Decimal = ZERO
    commission_rate: Decimal = ZERO
    fixed_channel_fee: Decimal = ZERO

    def __post_init__(self) -> None:
        _require_key(self.key, field="channel_sale.key")
        _require_positive_int(
            self.participant_count,
            field=f"channel_sale[{self.key}].participant_count",
        )
        gross = _require_non_negative(
            self.gross_revenue,
            field=f"channel_sale[{self.key}].gross_revenue",
        )
        reduction = _require_non_negative(
            self.revenue_reduction_amount,
            field=f"channel_sale[{self.key}].revenue_reduction_amount",
        )
        if reduction > gross:
            raise TourismInputError(
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
    def net_revenue_before_channel_fee(self) -> Decimal:
        return self.gross_revenue - self.revenue_reduction_amount

    @property
    def percentage_channel_fee(self) -> Decimal:
        return self.commission_base_amount * self.commission_rate

    @property
    def total_channel_fee(self) -> Decimal:
        return self.percentage_channel_fee + self.fixed_channel_fee

    @property
    def net_revenue_after_channel_fee(self) -> Decimal:
        return self.net_revenue_before_channel_fee - self.total_channel_fee


@dataclass(frozen=True)
class TourismComponentCost:
    """Variable-per-participant or fixed-package component amount."""

    key: str
    category: str
    scope: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="component.key")
        if self.category not in TOURISM_COMPONENT_CATEGORIES:
            raise TourismInputError(f"unsupported tourism component category: {self.category}")
        if self.scope not in COMPONENT_SCOPES:
            raise TourismInputError(f"unsupported tourism component scope: {self.scope}")
        _require_non_negative(self.amount, field=f"component[{self.key}].amount")

    def total_for_participants(self, participant_count: int) -> Decimal:
        if self.scope == "per_participant":
            return self.amount * Decimal(participant_count)
        return self.amount


@dataclass(frozen=True)
class TourismPackageResult:
    """Package economics before FX/tax/legal travel-policy treatment."""

    participant_count: int
    currency: str
    gross_revenue: Decimal
    revenue_reduction_amount: Decimal
    net_revenue_before_channel_fee: Decimal
    percentage_channel_fee: Decimal
    fixed_channel_fee: Decimal
    total_channel_fee: Decimal
    net_revenue_after_channel_fee: Decimal
    channel_revenue_totals: tuple[tuple[str, Decimal], ...]
    per_participant_component_cost: Decimal
    fixed_package_component_cost: Decimal
    total_package_cost: Decimal
    component_category_totals: tuple[tuple[str, Decimal], ...]
    cost_per_participant: Decimal
    net_revenue_per_participant: Decimal
    package_contribution: Decimal
    contribution_per_participant: Decimal
    contribution_margin_ratio: Decimal | None


def _ensure_unique_keys(
    items: Iterable[TourismChannelSale | TourismComponentCost],
) -> None:
    seen: set[str] = set()
    for item in items:
        if item.key in seen:
            raise TourismInputError(f"duplicate tourism line key: {item.key}")
        seen.add(item.key)


def _component_category_totals(
    components: Sequence[TourismComponentCost],
    participant_count: int,
) -> tuple[tuple[str, Decimal], ...]:
    totals: dict[str, Decimal] = {}
    for line in components:
        total = line.total_for_participants(participant_count)
        totals[line.category] = totals.get(line.category, ZERO) + total
    return tuple(sorted(totals.items()))


def _channel_revenue_totals(
    channel_sales: Sequence[TourismChannelSale],
) -> tuple[tuple[str, Decimal], ...]:
    return tuple(sorted((line.key, line.net_revenue_after_channel_fee) for line in channel_sales))


def calculate_tourism_package(
    *,
    plan: TourismPackagePlan,
    channel_sales: Sequence[TourismChannelSale],
    components: Sequence[TourismComponentCost],
) -> TourismPackageResult:
    """Calculate package economics from explicit participant, channel, and component inputs."""

    _ensure_unique_keys((*channel_sales, *components))
    sold_participants = sum(line.participant_count for line in channel_sales)
    if sold_participants != plan.participant_count:
        raise TourismInputError("channel participant_count must equal package participant_count")

    gross_revenue = sum((line.gross_revenue for line in channel_sales), ZERO)
    revenue_reduction = sum((line.revenue_reduction_amount for line in channel_sales), ZERO)
    net_before_channel = gross_revenue - revenue_reduction
    percentage_channel_fee = sum(
        (line.percentage_channel_fee for line in channel_sales),
        ZERO,
    )
    fixed_channel_fee = sum((line.fixed_channel_fee for line in channel_sales), ZERO)
    total_channel_fee = percentage_channel_fee + fixed_channel_fee
    net_after_channel = net_before_channel - total_channel_fee

    per_participant_component_cost = sum(
        (
            line.total_for_participants(plan.participant_count)
            for line in components
            if line.scope == "per_participant"
        ),
        ZERO,
    )
    fixed_package_component_cost = sum(
        (line.amount for line in components if line.scope == "fixed_package"),
        ZERO,
    )
    total_package_cost = per_participant_component_cost + fixed_package_component_cost
    participants = Decimal(plan.participant_count)
    cost_per_participant = total_package_cost / participants
    net_revenue_per_participant = net_after_channel / participants
    contribution = net_after_channel - total_package_cost
    contribution_per_participant = contribution / participants
    contribution_margin = contribution / net_after_channel if net_after_channel != ZERO else None

    return TourismPackageResult(
        participant_count=plan.participant_count,
        currency=plan.currency,
        gross_revenue=gross_revenue,
        revenue_reduction_amount=revenue_reduction,
        net_revenue_before_channel_fee=net_before_channel,
        percentage_channel_fee=percentage_channel_fee,
        fixed_channel_fee=fixed_channel_fee,
        total_channel_fee=total_channel_fee,
        net_revenue_after_channel_fee=net_after_channel,
        channel_revenue_totals=_channel_revenue_totals(channel_sales),
        per_participant_component_cost=per_participant_component_cost,
        fixed_package_component_cost=fixed_package_component_cost,
        total_package_cost=total_package_cost,
        component_category_totals=_component_category_totals(
            components,
            plan.participant_count,
        ),
        cost_per_participant=cost_per_participant,
        net_revenue_per_participant=net_revenue_per_participant,
        package_contribution=contribution,
        contribution_per_participant=contribution_per_participant,
        contribution_margin_ratio=contribution_margin,
    )


def as_core_direct_cost(
    result: TourismPackageResult,
    *,
    key: str = "tourism-package",
) -> CostLine:
    """Bridge package operating cost into the sector-neutral costing core."""

    _require_key(key, field="core_cost_key")
    return CostLine(key=key, amount=result.total_package_cost)


def build_tourism_snapshot(result: TourismPackageResult) -> dict[str, object]:
    """Serialize exact package economics without claiming FX/tax/legal treatment."""

    return {
        "engine_version": ENGINE_VERSION,
        "participant_count": result.participant_count,
        "currency": result.currency,
        "gross_revenue": str(result.gross_revenue),
        "revenue_reduction_amount": str(result.revenue_reduction_amount),
        "net_revenue_before_channel_fee": str(result.net_revenue_before_channel_fee),
        "percentage_channel_fee": str(result.percentage_channel_fee),
        "fixed_channel_fee": str(result.fixed_channel_fee),
        "total_channel_fee": str(result.total_channel_fee),
        "net_revenue_after_channel_fee": str(result.net_revenue_after_channel_fee),
        "channel_revenue_totals": {
            channel: str(amount) for channel, amount in result.channel_revenue_totals
        },
        "per_participant_component_cost": str(result.per_participant_component_cost),
        "fixed_package_component_cost": str(result.fixed_package_component_cost),
        "total_package_cost": str(result.total_package_cost),
        "component_category_totals": {
            category: str(amount) for category, amount in result.component_category_totals
        },
        "cost_per_participant": str(result.cost_per_participant),
        "net_revenue_per_participant": str(result.net_revenue_per_participant),
        "package_contribution": str(result.package_contribution),
        "contribution_per_participant": str(result.contribution_per_participant),
        "contribution_margin_ratio": (
            str(result.contribution_margin_ratio)
            if result.contribution_margin_ratio is not None
            else None
        ),
        "fx_conversion_applied": False,
        "fx_rate_inferred": False,
        "agency_fee_schedule_inferred": False,
        "tourism_tax_policy_applied": False,
        "vat_treatment_applied": False,
        "travel_package_legal_policy_applied": False,
    }
