"""Regression tests for the sector-neutral costing and pricing core."""

from decimal import Decimal

import pytest

from app.costing_engine import (
    AllocationWeight,
    CostingInputError,
    CostLine,
    RevenueLine,
    allocate_overhead,
    build_costing_snapshot,
    calculate_break_even_revenue,
    calculate_costing_statement,
    price_from_markup,
    price_from_sales_margin,
)


def test_costing_statement_preserves_pre_tax_accounting_flow() -> None:
    result = calculate_costing_statement(
        revenues=(RevenueLine("sales", Decimal("100000.00"), Decimal("5000.00")),),
        direct_costs=(CostLine("materials", Decimal("40000.00")),),
        overhead_costs=(CostLine("rent-share", Decimal("20000.00")),),
        depreciation_costs=(CostLine("equipment-depreciation", Decimal("5000.00")),),
        financing_costs=(CostLine("loan-interest", Decimal("3000.00")),),
    )

    assert result.gross_revenue == Decimal("100000.00")
    assert result.revenue_reductions == Decimal("5000.00")
    assert result.net_revenue == Decimal("95000.00")
    assert result.direct_costs == Decimal("40000.00")
    assert result.contribution_profit == Decimal("55000.00")
    assert result.overhead_costs == Decimal("20000.00")
    assert result.operating_profit_before_depreciation_and_financing == Decimal("35000.00")
    assert result.depreciation_costs == Decimal("5000.00")
    assert result.financing_costs == Decimal("3000.00")
    assert result.pretax_accounting_profit == Decimal("27000.00")
    assert result.contribution_margin_ratio == Decimal("55000.00") / Decimal("95000.00")
    assert result.pretax_accounting_margin_ratio == Decimal("27000.00") / Decimal("95000.00")


def test_costing_statement_can_report_loss_without_clamping_to_zero() -> None:
    result = calculate_costing_statement(
        revenues=(RevenueLine("sales", Decimal("10000.00")),),
        direct_costs=(CostLine("direct", Decimal("8000.00")),),
        overhead_costs=(CostLine("overhead", Decimal("3000.00")),),
        depreciation_costs=(CostLine("depreciation", Decimal("500.00")),),
        financing_costs=(CostLine("financing", Decimal("250.00")),),
    )
    assert result.pretax_accounting_profit == Decimal("-1750.00")
    assert result.pretax_accounting_margin_ratio == Decimal("-0.175")


def test_zero_net_revenue_has_no_fabricated_margin_ratio() -> None:
    result = calculate_costing_statement(
        revenues=(RevenueLine("sales", Decimal("0.00")),),
        direct_costs=(),
        overhead_costs=(),
        depreciation_costs=(),
        financing_costs=(),
    )
    assert result.contribution_margin_ratio is None
    assert result.pretax_accounting_margin_ratio is None


def test_revenue_reductions_cannot_exceed_gross() -> None:
    with pytest.raises(CostingInputError, match="cannot exceed"):
        RevenueLine("invalid", Decimal("100.00"), Decimal("100.01"))


def test_runtime_rejects_binary_float_even_if_type_checker_is_bypassed() -> None:
    with pytest.raises(CostingInputError, match="must be Decimal"):
        CostLine("float-cost", 1.5)  # type: ignore[arg-type]


def test_overhead_allocation_conserves_pool_exactly_and_is_order_independent() -> None:
    pool = CostLine("rent", Decimal("100.00"))
    weights = (
        AllocationWeight("product-c", Decimal("3")),
        AllocationWeight("product-a", Decimal("1")),
        AllocationWeight("product-b", Decimal("2")),
    )
    allocated = allocate_overhead(pool, weights)

    assert tuple(item.target_key for item in allocated) == (
        "product-a",
        "product-b",
        "product-c",
    )
    assert sum((item.amount for item in allocated), Decimal("0")) == pool.amount
    assert allocated[2].amount == Decimal("50.00")


def test_overhead_allocation_rejects_duplicate_target() -> None:
    with pytest.raises(CostingInputError, match="duplicate allocation target"):
        allocate_overhead(
            CostLine("rent", Decimal("100.00")),
            (
                AllocationWeight("same", Decimal("1")),
                AllocationWeight("same", Decimal("2")),
            ),
        )


def test_markup_and_sales_margin_are_not_conflated() -> None:
    markup = price_from_markup(Decimal("100.00"), Decimal("0.20"))
    margin = price_from_sales_margin(Decimal("100.00"), Decimal("0.20"))

    assert markup.price == Decimal("120.0000")
    assert markup.mode == "markup_on_cost"
    assert margin.price == Decimal("125.00")
    assert margin.mode == "margin_on_sales"


def test_sales_margin_rejects_one_hundred_percent_or_more() -> None:
    with pytest.raises(CostingInputError, match="less than 1"):
        price_from_sales_margin(Decimal("100.00"), Decimal("1.00"))


def test_break_even_revenue_uses_explicit_contribution_margin() -> None:
    result = calculate_break_even_revenue(Decimal("60000.00"), Decimal("0.40"))
    assert result.break_even_revenue == Decimal("150000.00")


def test_snapshot_explicitly_refuses_to_infer_taxable_base() -> None:
    statement = calculate_costing_statement(
        revenues=(RevenueLine("sales", Decimal("1000.00")),),
        direct_costs=(CostLine("direct", Decimal("400.00")),),
        overhead_costs=(CostLine("overhead", Decimal("100.00")),),
        depreciation_costs=(),
        financing_costs=(),
    )
    snapshot = build_costing_snapshot(statement)

    assert snapshot["statement_type"] == "pretax_accounting"
    assert snapshot["taxable_base_inferred"] is False
    assert snapshot["pretax_accounting_profit"] == "500.00"
    assert "tax" not in snapshot
    assert "net_profit_after_tax" not in snapshot
