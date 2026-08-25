"""Regression tests for deterministic accounting asset depreciation."""

from decimal import Decimal, Inexact, getcontext, setcontext

import pytest

from app.asset_depreciation import (
    AssetDepreciationInputError,
    build_asset_depreciation_snapshot,
    calculate_straight_line_depreciation,
)


def test_straight_line_depreciation_preserves_residual_value() -> None:
    result = calculate_straight_line_depreciation(
        asset_key="machine-1",
        acquisition_cost=Decimal("120000.00"),
        residual_value=Decimal("12000.00"),
        useful_life_months=36,
        elapsed_months=12,
    )

    assert result.depreciable_base == Decimal("108000.00")
    assert result.accumulated_depreciation == Decimal("36000.00")
    assert result.depreciation_for_period == Decimal("3000.00")
    assert result.carrying_amount == Decimal("84000.00")


def test_final_period_conserves_exact_depreciable_base() -> None:
    result = calculate_straight_line_depreciation(
        asset_key="repeating-base",
        acquisition_cost=Decimal("100.00"),
        residual_value=Decimal("0"),
        useful_life_months=3,
        elapsed_months=3,
    )

    assert result.accumulated_depreciation == Decimal("100.00")
    assert result.carrying_amount == Decimal("0.00")
    assert result.depreciation_for_period > Decimal("33.33")


def test_before_first_period_has_zero_depreciation() -> None:
    result = calculate_straight_line_depreciation(
        asset_key="new-asset",
        acquisition_cost=Decimal("5000.00"),
        residual_value=Decimal("500.00"),
        useful_life_months=12,
        elapsed_months=0,
    )

    assert result.depreciation_for_period == Decimal("0")
    assert result.accumulated_depreciation == Decimal("0")
    assert result.carrying_amount == Decimal("5000.00")


def test_repeating_depreciation_is_independent_of_all_caller_context_settings() -> None:
    original_context = getcontext().copy()
    try:
        getcontext().prec = 5
        getcontext().Emax = 5
        getcontext().traps[Inexact] = True
        constrained = calculate_straight_line_depreciation(
            asset_key="context-test",
            acquisition_cost=Decimal("100"),
            residual_value=Decimal("0"),
            useful_life_months=3,
            elapsed_months=2,
        )

        setcontext(original_context.copy())
        getcontext().prec = 50
        unconstrained = calculate_straight_line_depreciation(
            asset_key="context-test",
            acquisition_cost=Decimal("100"),
            residual_value=Decimal("0"),
            useful_life_months=3,
            elapsed_months=2,
        )
    finally:
        setcontext(original_context)

    assert constrained == unconstrained
    assert constrained.accumulated_depreciation == Decimal(
        "66.66666666666666666666666666666666666666666666666666666666666666666666666667"
    )


def test_supported_precision_preserves_small_residual_on_large_asset() -> None:
    result = calculate_straight_line_depreciation(
        asset_key="large-asset",
        acquisition_cost=Decimal("99999999999999999999999999999999999999"),
        residual_value=Decimal("0.01"),
        useful_life_months=1,
        elapsed_months=1,
    )

    assert result.carrying_amount == Decimal("0.01")
    assert result.accumulated_depreciation == Decimal(
        "99999999999999999999999999999999999998.99"
    )


def test_inputs_beyond_supported_precision_fail_closed() -> None:
    with pytest.raises(AssetDepreciationInputError, match="exceeds 38 significant digits"):
        calculate_straight_line_depreciation(
            asset_key="too-precise",
            acquisition_cost=Decimal("999999999999999999999999999999999999999"),
            residual_value=Decimal("0"),
            useful_life_months=12,
            elapsed_months=1,
        )

    with pytest.raises(AssetDepreciationInputError, match="exceeds scale 18"):
        calculate_straight_line_depreciation(
            asset_key="too-scaled",
            acquisition_cost=Decimal("1.0000000000000000001"),
            residual_value=Decimal("0"),
            useful_life_months=12,
            elapsed_months=1,
        )


def test_invalid_asset_assumptions_fail_closed() -> None:
    with pytest.raises(AssetDepreciationInputError, match="cannot exceed"):
        calculate_straight_line_depreciation(
            asset_key="invalid-residual",
            acquisition_cost=Decimal("100.00"),
            residual_value=Decimal("100.01"),
            useful_life_months=12,
            elapsed_months=1,
        )

    with pytest.raises(AssetDepreciationInputError, match="cannot exceed useful_life"):
        calculate_straight_line_depreciation(
            asset_key="past-life",
            acquisition_cost=Decimal("100.00"),
            residual_value=Decimal("0"),
            useful_life_months=12,
            elapsed_months=13,
        )

    with pytest.raises(AssetDepreciationInputError, match="must be int"):
        calculate_straight_line_depreciation(
            asset_key="bool-life",
            acquisition_cost=Decimal("100.00"),
            residual_value=Decimal("0"),
            useful_life_months=True,  # type: ignore[arg-type]
            elapsed_months=1,
        )


def test_binary_float_fails_closed() -> None:
    with pytest.raises(AssetDepreciationInputError, match="must be Decimal"):
        calculate_straight_line_depreciation(
            asset_key="float-cost",
            acquisition_cost=100.0,  # type: ignore[arg-type]
            residual_value=Decimal("0"),
            useful_life_months=12,
            elapsed_months=1,
        )


def test_snapshot_records_accounting_method_and_refuses_tax_inference() -> None:
    result = calculate_straight_line_depreciation(
        asset_key="machine-1",
        acquisition_cost=Decimal("120000.00"),
        residual_value=Decimal("12000.00"),
        useful_life_months=36,
        elapsed_months=12,
    )
    snapshot = build_asset_depreciation_snapshot(result)

    assert snapshot["engine_version"] == "asset-depreciation-v1"
    assert snapshot["method"] == "straight_line_book"
    assert snapshot["decimal_policy"] == {
        "precision": 76,
        "rounding": "ROUND_HALF_EVEN",
        "emin": -999999,
        "emax": 999999,
        "implicit_currency_rounding": False,
        "max_input_significant_digits": 38,
        "max_input_scale": 18,
        "max_input_integer_digits": 38,
    }
    assert snapshot["statutory_tax_rate_inferred"] is False
    assert snapshot["tax_deductibility_inferred"] is False
    assert snapshot["residual_value_inferred"] is False
    assert snapshot["useful_life_inferred"] is False
