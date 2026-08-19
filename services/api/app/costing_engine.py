"""Sector-neutral Decimal costing and pre-tax profitability primitives.

This module deliberately stops at accounting profit before tax. It does not
assume that accounting profit equals a taxable base; tax-base reconciliation is
an explicit future contract.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

ENGINE_VERSION = "core-costing-v1"
ZERO = Decimal("0")
ONE = Decimal("1")


class CostingInputError(ValueError):
    """Raised when financial inputs violate the costing contract."""


def _require_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise CostingInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise CostingInputError(f"{field} must be finite")
    return value


def _require_non_negative(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value < ZERO:
        raise CostingInputError(f"{field} must be non-negative")
    return decimal_value


def _require_key(value: str, *, field: str) -> None:
    if not value.strip():
        raise CostingInputError(f"{field} must not be blank")


@dataclass(frozen=True)
class RevenueLine:
    """A gross revenue line with explicit reductions such as discounts/returns."""

    key: str
    gross_amount: Decimal
    reductions: Decimal = ZERO

    def __post_init__(self) -> None:
        _require_key(self.key, field="revenue.key")
        gross = _require_non_negative(self.gross_amount, field=f"revenue[{self.key}].gross_amount")
        reductions = _require_non_negative(
            self.reductions,
            field=f"revenue[{self.key}].reductions",
        )
        if reductions > gross:
            raise CostingInputError(f"revenue[{self.key}].reductions cannot exceed gross_amount")

    @property
    def net_amount(self) -> Decimal:
        return self.gross_amount - self.reductions


@dataclass(frozen=True)
class CostLine:
    """A non-negative monetary cost already measured for the calculation period."""

    key: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="cost.key")
        _require_non_negative(self.amount, field=f"cost[{self.key}].amount")


@dataclass(frozen=True)
class AllocationWeight:
    """A positive allocation basis unit for one target."""

    target_key: str
    weight: Decimal

    def __post_init__(self) -> None:
        _require_key(self.target_key, field="allocation.target_key")
        weight = _require_decimal(self.weight, field=f"allocation[{self.target_key}].weight")
        if weight <= ZERO:
            raise CostingInputError(f"allocation[{self.target_key}].weight must be positive")


@dataclass(frozen=True)
class AllocatedCost:
    """One deterministic share of an overhead pool."""

    pool_key: str
    target_key: str
    amount: Decimal
    weight: Decimal
    total_weight: Decimal


@dataclass(frozen=True)
class CostingStatement:
    """Sector-neutral pre-tax accounting statement for one calculation scope."""

    gross_revenue: Decimal
    revenue_reductions: Decimal
    net_revenue: Decimal
    direct_costs: Decimal
    contribution_profit: Decimal
    overhead_costs: Decimal
    operating_profit_before_depreciation_and_financing: Decimal
    depreciation_costs: Decimal
    financing_costs: Decimal
    pretax_accounting_profit: Decimal
    contribution_margin_ratio: Decimal | None
    pretax_accounting_margin_ratio: Decimal | None


@dataclass(frozen=True)
class PricingResult:
    cost_base: Decimal
    rate: Decimal
    price: Decimal
    mode: str


@dataclass(frozen=True)
class BreakEvenResult:
    fixed_costs: Decimal
    contribution_margin_ratio: Decimal
    break_even_revenue: Decimal


def _ensure_unique_keys(items: Iterable[RevenueLine | CostLine], *, group: str) -> None:
    seen: set[str] = set()
    for item in items:
        if item.key in seen:
            raise CostingInputError(f"duplicate {group} key: {item.key}")
        seen.add(item.key)


def _sum_costs(lines: Iterable[CostLine | AllocatedCost]) -> Decimal:
    return sum((line.amount for line in lines), ZERO)


def allocate_overhead(
    pool: CostLine,
    weights: Sequence[AllocationWeight],
) -> tuple[AllocatedCost, ...]:
    """Allocate an overhead pool proportionally while conserving it exactly.

    Targets are sorted by key so allocation does not depend on caller order.
    Decimal division may be repeating; the final target receives the exact
    residual so allocated shares always sum to the original pool without a
    hidden currency-rounding policy.
    """

    if not weights:
        raise CostingInputError("allocation weights must not be empty")
    ordered = sorted(weights, key=lambda item: item.target_key)
    seen: set[str] = set()
    for item in ordered:
        if item.target_key in seen:
            raise CostingInputError(f"duplicate allocation target: {item.target_key}")
        seen.add(item.target_key)

    total_weight = sum((item.weight for item in ordered), ZERO)
    if total_weight <= ZERO:
        raise CostingInputError("allocation total weight must be positive")

    allocations: list[AllocatedCost] = []
    allocated_so_far = ZERO
    last_index = len(ordered) - 1
    for index, item in enumerate(ordered):
        if index == last_index:
            amount = pool.amount - allocated_so_far
        else:
            amount = pool.amount * item.weight / total_weight
            allocated_so_far += amount
        allocations.append(
            AllocatedCost(
                pool_key=pool.key,
                target_key=item.target_key,
                amount=amount,
                weight=item.weight,
                total_weight=total_weight,
            )
        )
    return tuple(allocations)


def calculate_costing_statement(
    *,
    revenues: Sequence[RevenueLine],
    direct_costs: Sequence[CostLine],
    overhead_costs: Sequence[CostLine | AllocatedCost],
    depreciation_costs: Sequence[CostLine],
    financing_costs: Sequence[CostLine],
) -> CostingStatement:
    """Build an exact pre-tax accounting statement without tax-base inference."""

    _ensure_unique_keys(revenues, group="revenue")
    _ensure_unique_keys(direct_costs, group="direct cost")
    _ensure_unique_keys(depreciation_costs, group="depreciation cost")
    _ensure_unique_keys(financing_costs, group="financing cost")

    gross_revenue = sum((line.gross_amount for line in revenues), ZERO)
    reductions = sum((line.reductions for line in revenues), ZERO)
    net_revenue = gross_revenue - reductions
    direct_total = _sum_costs(direct_costs)
    overhead_total = _sum_costs(overhead_costs)
    depreciation_total = _sum_costs(depreciation_costs)
    financing_total = _sum_costs(financing_costs)

    contribution_profit = net_revenue - direct_total
    operating_profit = contribution_profit - overhead_total
    pretax_profit = operating_profit - depreciation_total - financing_total

    contribution_margin = None
    pretax_margin = None
    if net_revenue > ZERO:
        contribution_margin = contribution_profit / net_revenue
        pretax_margin = pretax_profit / net_revenue

    return CostingStatement(
        gross_revenue=gross_revenue,
        revenue_reductions=reductions,
        net_revenue=net_revenue,
        direct_costs=direct_total,
        contribution_profit=contribution_profit,
        overhead_costs=overhead_total,
        operating_profit_before_depreciation_and_financing=operating_profit,
        depreciation_costs=depreciation_total,
        financing_costs=financing_total,
        pretax_accounting_profit=pretax_profit,
        contribution_margin_ratio=contribution_margin,
        pretax_accounting_margin_ratio=pretax_margin,
    )


def price_from_markup(cost_base: Decimal, markup_rate: Decimal) -> PricingResult:
    """Calculate price when markup is expressed as a percentage of cost."""

    cost = _require_non_negative(cost_base, field="cost_base")
    markup = _require_non_negative(markup_rate, field="markup_rate")
    return PricingResult(
        cost_base=cost,
        rate=markup,
        price=cost * (ONE + markup),
        mode="markup_on_cost",
    )


def price_from_sales_margin(cost_base: Decimal, margin_rate: Decimal) -> PricingResult:
    """Calculate price when target margin is expressed as a percentage of sales."""

    cost = _require_non_negative(cost_base, field="cost_base")
    margin = _require_non_negative(margin_rate, field="margin_rate")
    if margin >= ONE:
        raise CostingInputError("margin_rate must be less than 1")
    return PricingResult(
        cost_base=cost,
        rate=margin,
        price=cost / (ONE - margin),
        mode="margin_on_sales",
    )


def calculate_break_even_revenue(
    fixed_costs: Decimal,
    contribution_margin_ratio: Decimal,
) -> BreakEvenResult:
    """Calculate revenue required to cover fixed costs at a given contribution margin."""

    fixed = _require_non_negative(fixed_costs, field="fixed_costs")
    ratio = _require_decimal(contribution_margin_ratio, field="contribution_margin_ratio")
    if ratio <= ZERO or ratio > ONE:
        raise CostingInputError("contribution_margin_ratio must be greater than 0 and at most 1")
    return BreakEvenResult(
        fixed_costs=fixed,
        contribution_margin_ratio=ratio,
        break_even_revenue=fixed / ratio,
    )


def build_costing_snapshot(statement: CostingStatement) -> dict[str, object]:
    """Serialize exact statement values as decimal strings for calculation snapshots."""

    return {
        "engine_version": ENGINE_VERSION,
        "statement_type": "pretax_accounting",
        "taxable_base_inferred": False,
        "gross_revenue": str(statement.gross_revenue),
        "revenue_reductions": str(statement.revenue_reductions),
        "net_revenue": str(statement.net_revenue),
        "direct_costs": str(statement.direct_costs),
        "contribution_profit": str(statement.contribution_profit),
        "overhead_costs": str(statement.overhead_costs),
        "operating_profit_before_depreciation_and_financing": str(
            statement.operating_profit_before_depreciation_and_financing
        ),
        "depreciation_costs": str(statement.depreciation_costs),
        "financing_costs": str(statement.financing_costs),
        "pretax_accounting_profit": str(statement.pretax_accounting_profit),
        "contribution_margin_ratio": (
            str(statement.contribution_margin_ratio)
            if statement.contribution_margin_ratio is not None
            else None
        ),
        "pretax_accounting_margin_ratio": (
            str(statement.pretax_accounting_margin_ratio)
            if statement.pretax_accounting_margin_ratio is not None
            else None
        ),
    }
