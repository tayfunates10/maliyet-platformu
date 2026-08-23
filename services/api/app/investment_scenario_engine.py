"""Decimal-only investment return and explicit scenario primitives.

The engine does not infer tax, financing, inflation, discount rates, or scenario
assumptions. Callers must provide already-defined monetary values for the same
analysis period and currency context.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

ENGINE_VERSION = "investment-scenario-v1"
ZERO = Decimal("0")
SCENARIO_KEYS = ("pessimistic", "normal", "optimistic")


class InvestmentScenarioInputError(ValueError):
    """Raised when investment or scenario inputs violate the domain contract."""


def _require_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise InvestmentScenarioInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise InvestmentScenarioInputError(f"{field} must be finite")
    return value


def _require_non_negative(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value < ZERO:
        raise InvestmentScenarioInputError(f"{field} must be non-negative")
    return decimal_value


def _require_positive(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value <= ZERO:
        raise InvestmentScenarioInputError(f"{field} must be positive")
    return decimal_value


@dataclass(frozen=True)
class InvestmentMetricInputs:
    """Explicit denominators/numerators for ROI, ROE and ROIC.

    `net_operating_profit_after_tax` is deliberately caller-provided. This
    module never derives NOPAT from a tax rate or accounting profit.
    """

    initial_investment: Decimal
    net_return: Decimal
    equity: Decimal
    net_income: Decimal
    invested_capital: Decimal
    net_operating_profit_after_tax: Decimal

    def __post_init__(self) -> None:
        _require_positive(self.initial_investment, field="initial_investment")
        _require_decimal(self.net_return, field="net_return")
        _require_positive(self.equity, field="equity")
        _require_decimal(self.net_income, field="net_income")
        _require_positive(self.invested_capital, field="invested_capital")
        _require_decimal(
            self.net_operating_profit_after_tax,
            field="net_operating_profit_after_tax",
        )


@dataclass(frozen=True)
class InvestmentMetrics:
    initial_investment: Decimal
    equity: Decimal
    invested_capital: Decimal
    roi_ratio: Decimal
    roe_ratio: Decimal
    roic_ratio: Decimal


@dataclass(frozen=True)
class ScenarioCase:
    """One explicit management scenario in a single period/currency context."""

    key: str
    revenue: Decimal
    costs: Decimal

    def __post_init__(self) -> None:
        if self.key not in SCENARIO_KEYS:
            raise InvestmentScenarioInputError(
                f"scenario.key must be one of: {', '.join(SCENARIO_KEYS)}"
            )
        _require_non_negative(self.revenue, field=f"scenario[{self.key}].revenue")
        _require_non_negative(self.costs, field=f"scenario[{self.key}].costs")


@dataclass(frozen=True)
class ScenarioOutcome:
    key: str
    revenue: Decimal
    costs: Decimal
    profit: Decimal
    profit_margin_ratio: Decimal | None


def calculate_investment_metrics(inputs: InvestmentMetricInputs) -> InvestmentMetrics:
    """Calculate exact ROI/ROE/ROIC ratios from explicit Decimal inputs."""

    return InvestmentMetrics(
        initial_investment=inputs.initial_investment,
        equity=inputs.equity,
        invested_capital=inputs.invested_capital,
        roi_ratio=inputs.net_return / inputs.initial_investment,
        roe_ratio=inputs.net_income / inputs.equity,
        roic_ratio=inputs.net_operating_profit_after_tax / inputs.invested_capital,
    )


def calculate_scenarios(cases: Sequence[ScenarioCase]) -> tuple[ScenarioOutcome, ...]:
    """Calculate the canonical pessimistic/normal/optimistic scenario set.

    The three cases are explicit inputs rather than generated percentage
    shocks. Profit ordering is validated so accidentally mislabeled scenarios
    fail closed instead of producing a misleading comparison.
    """

    by_key: dict[str, ScenarioCase] = {}
    for case in cases:
        if case.key in by_key:
            raise InvestmentScenarioInputError(f"duplicate scenario key: {case.key}")
        by_key[case.key] = case

    missing = [key for key in SCENARIO_KEYS if key not in by_key]
    if missing or len(by_key) != len(SCENARIO_KEYS):
        raise InvestmentScenarioInputError(
            "scenario set must contain exactly pessimistic, normal and optimistic"
        )

    outcomes: list[ScenarioOutcome] = []
    for key in SCENARIO_KEYS:
        case = by_key[key]
        profit = case.revenue - case.costs
        margin = None if case.revenue == ZERO else profit / case.revenue
        outcomes.append(
            ScenarioOutcome(
                key=key,
                revenue=case.revenue,
                costs=case.costs,
                profit=profit,
                profit_margin_ratio=margin,
            )
        )

    if not (outcomes[0].profit <= outcomes[1].profit <= outcomes[2].profit):
        raise InvestmentScenarioInputError(
            "scenario profit ordering must be pessimistic <= normal <= optimistic"
        )
    return tuple(outcomes)


def build_investment_scenario_snapshot(
    *,
    metrics: InvestmentMetrics,
    scenarios: Sequence[ScenarioOutcome],
) -> dict[str, object]:
    """Return a deterministic Decimal-string snapshot without hidden policy claims."""

    if tuple(item.key for item in scenarios) != SCENARIO_KEYS:
        raise InvestmentScenarioInputError("scenario outcomes must use canonical order")

    return {
        "engine_version": ENGINE_VERSION,
        "investment": {
            "initial_investment": str(metrics.initial_investment),
            "equity": str(metrics.equity),
            "invested_capital": str(metrics.invested_capital),
            "roi_ratio": str(metrics.roi_ratio),
            "roe_ratio": str(metrics.roe_ratio),
            "roic_ratio": str(metrics.roic_ratio),
        },
        "scenarios": [
            {
                "key": item.key,
                "revenue": str(item.revenue),
                "costs": str(item.costs),
                "profit": str(item.profit),
                "profit_margin_ratio": (
                    None if item.profit_margin_ratio is None else str(item.profit_margin_ratio)
                ),
            }
            for item in scenarios
        ],
        "policy": {
            "tax_rate_inferred": False,
            "financing_mix_inferred": False,
            "inflation_inferred": False,
            "discount_rate_inferred": False,
            "scenario_shocks_inferred": False,
        },
    }
