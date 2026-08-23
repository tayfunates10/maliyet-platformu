from decimal import Decimal

import pytest

from app.investment_scenario_engine import (
    InvestmentMetricInputs,
    InvestmentScenarioInputError,
    ScenarioCase,
    build_investment_scenario_snapshot,
    calculate_investment_metrics,
    calculate_scenarios,
)


def _metrics():
    return calculate_investment_metrics(
        InvestmentMetricInputs(
            initial_investment=Decimal("1000"),
            net_return=Decimal("150"),
            equity=Decimal("500"),
            net_income=Decimal("75"),
            invested_capital=Decimal("800"),
            net_operating_profit_after_tax=Decimal("96"),
        )
    )


def _scenarios():
    return calculate_scenarios(
        (
            ScenarioCase("optimistic", Decimal("1500"), Decimal("900")),
            ScenarioCase("pessimistic", Decimal("800"), Decimal("950")),
            ScenarioCase("normal", Decimal("1200"), Decimal("900")),
        )
    )


def test_roi_roe_roic_use_explicit_decimal_inputs() -> None:
    metrics = _metrics()

    assert metrics.roi_ratio == Decimal("0.15")
    assert metrics.roe_ratio == Decimal("0.15")
    assert metrics.roic_ratio == Decimal("0.12")


def test_negative_returns_are_preserved() -> None:
    metrics = calculate_investment_metrics(
        InvestmentMetricInputs(
            initial_investment=Decimal("100"),
            net_return=Decimal("-20"),
            equity=Decimal("80"),
            net_income=Decimal("-10"),
            invested_capital=Decimal("90"),
            net_operating_profit_after_tax=Decimal("-9"),
        )
    )

    assert metrics.roi_ratio == Decimal("-0.2")
    assert metrics.roe_ratio == Decimal("-0.125")
    assert metrics.roic_ratio == Decimal("-0.1")


@pytest.mark.parametrize("field", ["initial_investment", "equity", "invested_capital"])
def test_ratio_denominators_must_be_positive(field: str) -> None:
    values = {
        "initial_investment": Decimal("100"),
        "net_return": Decimal("10"),
        "equity": Decimal("80"),
        "net_income": Decimal("8"),
        "invested_capital": Decimal("90"),
        "net_operating_profit_after_tax": Decimal("9"),
    }
    values[field] = Decimal("0")

    with pytest.raises(InvestmentScenarioInputError, match="must be positive"):
        InvestmentMetricInputs(**values)


def test_binary_float_is_rejected() -> None:
    with pytest.raises(InvestmentScenarioInputError, match="must be Decimal"):
        InvestmentMetricInputs(
            initial_investment=100.0,  # type: ignore[arg-type]
            net_return=Decimal("10"),
            equity=Decimal("80"),
            net_income=Decimal("8"),
            invested_capital=Decimal("90"),
            net_operating_profit_after_tax=Decimal("9"),
        )


def test_scenarios_are_returned_in_canonical_order() -> None:
    outcomes = _scenarios()

    assert [item.key for item in outcomes] == ["pessimistic", "normal", "optimistic"]
    assert [item.profit for item in outcomes] == [
        Decimal("-150"),
        Decimal("300"),
        Decimal("600"),
    ]
    assert outcomes[0].profit_margin_ratio == Decimal("-0.1875")
    assert outcomes[1].profit_margin_ratio == Decimal("0.25")
    assert outcomes[2].profit_margin_ratio == Decimal("0.4")


def test_zero_revenue_does_not_fabricate_margin() -> None:
    outcomes = calculate_scenarios(
        (
            ScenarioCase("pessimistic", Decimal("0"), Decimal("10")),
            ScenarioCase("normal", Decimal("20"), Decimal("10")),
            ScenarioCase("optimistic", Decimal("30"), Decimal("10")),
        )
    )

    assert outcomes[0].profit == Decimal("-10")
    assert outcomes[0].profit_margin_ratio is None


def test_scenario_set_requires_exact_three_canonical_keys() -> None:
    with pytest.raises(InvestmentScenarioInputError, match="exactly pessimistic"):
        calculate_scenarios(
            (
                ScenarioCase("pessimistic", Decimal("80"), Decimal("90")),
                ScenarioCase("normal", Decimal("100"), Decimal("90")),
            )
        )


def test_duplicate_scenario_key_fails_closed() -> None:
    with pytest.raises(InvestmentScenarioInputError, match="duplicate scenario key"):
        calculate_scenarios(
            (
                ScenarioCase("pessimistic", Decimal("80"), Decimal("90")),
                ScenarioCase("normal", Decimal("100"), Decimal("90")),
                ScenarioCase("normal", Decimal("110"), Decimal("90")),
                ScenarioCase("optimistic", Decimal("120"), Decimal("90")),
            )
        )


def test_mislabeled_profit_ordering_fails_closed() -> None:
    with pytest.raises(InvestmentScenarioInputError, match="profit ordering"):
        calculate_scenarios(
            (
                ScenarioCase("pessimistic", Decimal("120"), Decimal("80")),
                ScenarioCase("normal", Decimal("100"), Decimal("90")),
                ScenarioCase("optimistic", Decimal("110"), Decimal("90")),
            )
        )


def test_snapshot_preserves_decimal_strings_and_policy_boundaries() -> None:
    snapshot = build_investment_scenario_snapshot(metrics=_metrics(), scenarios=_scenarios())

    assert snapshot["engine_version"] == "investment-scenario-v1"
    investment = snapshot["investment"]
    assert isinstance(investment, dict)
    assert investment["roi_ratio"] == "0.15"
    assert investment["roe_ratio"] == "0.15"
    assert investment["roic_ratio"] == "0.12"

    policy = snapshot["policy"]
    assert isinstance(policy, dict)
    assert policy == {
        "tax_rate_inferred": False,
        "financing_mix_inferred": False,
        "inflation_inferred": False,
        "discount_rate_inferred": False,
        "scenario_shocks_inferred": False,
    }
