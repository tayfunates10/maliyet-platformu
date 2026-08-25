"""Regression tests for deterministic target-profit pricing."""

from decimal import Decimal, Inexact, getcontext, setcontext

import pytest

from app.target_profit_pricing import (
    TargetProfitPricingInputError,
    build_target_profit_pricing_snapshot,
    calculate_target_profit_price,
)


def test_target_profit_price_uses_explicit_cost_profit_and_volume() -> None:
    result = calculate_target_profit_price(
        variable_cost_per_unit=Decimal("40.00"),
        fixed_costs=Decimal("30000.00"),
        target_profit=Decimal("20000.00"),
        expected_units=Decimal("1000"),
    )

    assert result.required_contribution_total == Decimal("50000.00")
    assert result.required_contribution_per_unit == Decimal("50.00")
    assert result.required_price_per_unit == Decimal("90.00")
    assert result.required_revenue == Decimal("90000.00")


def test_zero_target_profit_reduces_to_cost_recovery_price() -> None:
    result = calculate_target_profit_price(
        variable_cost_per_unit=Decimal("25.00"),
        fixed_costs=Decimal("15000.00"),
        target_profit=Decimal("0"),
        expected_units=Decimal("1000"),
    )

    assert result.required_price_per_unit == Decimal("40.00")
    assert result.required_revenue == Decimal("40000.00")


def test_expected_units_must_be_positive() -> None:
    with pytest.raises(TargetProfitPricingInputError, match="greater than 0"):
        calculate_target_profit_price(
            variable_cost_per_unit=Decimal("25.00"),
            fixed_costs=Decimal("1000.00"),
            target_profit=Decimal("500.00"),
            expected_units=Decimal("0"),
        )


def test_runtime_rejects_binary_float_inputs() -> None:
    with pytest.raises(TargetProfitPricingInputError, match="must be Decimal"):
        calculate_target_profit_price(
            variable_cost_per_unit=1.25,  # type: ignore[arg-type]
            fixed_costs=Decimal("1000.00"),
            target_profit=Decimal("500.00"),
            expected_units=Decimal("100"),
        )


def test_repeating_division_is_independent_of_full_caller_decimal_context() -> None:
    original_context = getcontext().copy()
    try:
        getcontext().prec = 5
        getcontext().Emax = 5
        getcontext().traps[Inexact] = True
        constrained = calculate_target_profit_price(
            variable_cost_per_unit=Decimal("1"),
            fixed_costs=Decimal("1"),
            target_profit=Decimal("0"),
            expected_units=Decimal("3"),
        )

        setcontext(original_context.copy())
        getcontext().prec = 50
        unconstrained = calculate_target_profit_price(
            variable_cost_per_unit=Decimal("1"),
            fixed_costs=Decimal("1"),
            target_profit=Decimal("0"),
            expected_units=Decimal("3"),
        )
    finally:
        setcontext(original_context)

    assert constrained == unconstrained
    assert constrained.required_contribution_per_unit == Decimal(
        "0.33333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333"
    )


def test_supported_maximum_magnitudes_preserve_fractional_fixed_cost() -> None:
    maximum = Decimal("99999999999999999999999999999999999999")
    result = calculate_target_profit_price(
        variable_cost_per_unit=maximum,
        fixed_costs=Decimal("0.01"),
        target_profit=Decimal("0"),
        expected_units=maximum,
    )

    variable_total = maximum * maximum
    assert result.required_revenue == variable_total + Decimal("0.01")
    assert result.required_revenue - variable_total == Decimal("0.01")


def test_inputs_beyond_supported_precision_fail_closed() -> None:
    with pytest.raises(TargetProfitPricingInputError, match="significant digits"):
        calculate_target_profit_price(
            variable_cost_per_unit=Decimal("123456789012345678901234567890123456789"),
            fixed_costs=Decimal("0"),
            target_profit=Decimal("0"),
            expected_units=Decimal("1"),
        )

    with pytest.raises(TargetProfitPricingInputError, match="scale 18"):
        calculate_target_profit_price(
            variable_cost_per_unit=Decimal("0.0000000000000000001"),
            fixed_costs=Decimal("0"),
            target_profit=Decimal("0"),
            expected_units=Decimal("1"),
        )


def test_snapshot_records_decimal_policy_and_refuses_tax_inference() -> None:
    result = calculate_target_profit_price(
        variable_cost_per_unit=Decimal("40.00"),
        fixed_costs=Decimal("30000.00"),
        target_profit=Decimal("20000.00"),
        expected_units=Decimal("1000"),
    )
    snapshot = build_target_profit_pricing_snapshot(result)

    assert snapshot["engine_version"] == "target-profit-pricing-v2"
    assert snapshot["decimal_policy"] == {
        "precision": 128,
        "rounding": "ROUND_HALF_EVEN",
        "emin": -999999,
        "emax": 999999,
        "max_input_significant_digits": 38,
        "max_input_scale": 18,
        "max_input_integer_digits": 38,
        "implicit_currency_rounding": False,
    }
    assert snapshot["required_price_per_unit"] == "90.00"
    assert snapshot["tax_inferred"] is False
    assert "tax_rate" not in snapshot
