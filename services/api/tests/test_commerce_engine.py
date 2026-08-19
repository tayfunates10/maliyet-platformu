"""Regression tests for trade and e-commerce order economics."""

from decimal import Decimal

import pytest

from app.commerce_engine import (
    CommerceFixedFee,
    CommerceInputError,
    CommerceOperatingCost,
    CommerceRateFee,
    CommerceSale,
    build_commerce_snapshot,
    calculate_commerce_result,
)


def test_ecommerce_order_calculates_explicit_channel_economics() -> None:
    result = calculate_commerce_result(
        sales=(
            CommerceSale(
                "product",
                quantity=Decimal("10"),
                unit_sale_price=Decimal("100.00"),
                unit_acquisition_cost=Decimal("40.00"),
                discount_amount=Decimal("100.00"),
            ),
        ),
        operating_costs=(
            CommerceOperatingCost("inbound", "inbound_freight", Decimal("30.00")),
            CommerceOperatingCost("fulfillment", "fulfillment", Decimal("20.00")),
            CommerceOperatingCost("ads", "advertising", Decimal("100.00")),
        ),
        rate_fees=(
            CommerceRateFee(
                "marketplace",
                "marketplace_commission",
                base_amount=Decimal("1000.00"),
                rate=Decimal("0.15"),
            ),
            CommerceRateFee(
                "payment",
                "payment_fee",
                base_amount=Decimal("900.00"),
                rate=Decimal("0.02"),
            ),
        ),
        fixed_fees=(CommerceFixedFee("channel-fixed", "channel_fee", Decimal("5.00")),),
    )

    assert result.gross_sales == Decimal("1000.00")
    assert result.discount_amount == Decimal("100.00")
    assert result.net_sales == Decimal("900.00")
    assert result.net_acquisition_cost == Decimal("400.00")
    assert result.operating_cost == Decimal("150.00")
    assert result.rate_fee_cost == Decimal("168.0000")
    assert result.fixed_fee_cost == Decimal("5.00")
    assert result.total_channel_cost == Decimal("173.0000")
    assert result.contribution_profit == Decimal("177.0000")
    assert result.contribution_margin_ratio == Decimal("177.0000") / Decimal("900.00")


def test_rate_fee_uses_caller_supplied_base_instead_of_inferred_sales_base() -> None:
    fee = CommerceRateFee(
        "custom-base",
        "marketplace_commission",
        base_amount=Decimal("500.00"),
        rate=Decimal("0.10"),
    )
    assert fee.amount == Decimal("50.0000")


def test_return_allowance_and_inventory_recovery_are_separate_explicit_inputs() -> None:
    result = calculate_commerce_result(
        sales=(
            CommerceSale(
                "returns",
                quantity=Decimal("2"),
                unit_sale_price=Decimal("100.00"),
                unit_acquisition_cost=Decimal("50.00"),
                return_allowance_amount=Decimal("40.00"),
                inventory_recovery_credit=Decimal("25.00"),
            ),
        ),
        operating_costs=(
            CommerceOperatingCost("return-work", "return_handling", Decimal("10.00")),
        ),
        rate_fees=(),
        fixed_fees=(),
    )

    assert result.return_allowance_amount == Decimal("40.00")
    assert result.net_sales == Decimal("160.00")
    assert result.gross_acquisition_cost == Decimal("100.00")
    assert result.inventory_recovery_credit == Decimal("25.00")
    assert result.net_acquisition_cost == Decimal("75.00")
    assert result.contribution_profit == Decimal("75.00")


def test_revenue_reductions_cannot_exceed_gross_sales() -> None:
    with pytest.raises(CommerceInputError, match="cannot exceed gross sales"):
        CommerceSale(
            "bad-reduction",
            quantity=Decimal("1"),
            unit_sale_price=Decimal("100.00"),
            unit_acquisition_cost=Decimal("10.00"),
            discount_amount=Decimal("60.00"),
            return_allowance_amount=Decimal("41.00"),
        )


def test_inventory_recovery_cannot_exceed_acquisition_cost() -> None:
    with pytest.raises(CommerceInputError, match="cannot exceed acquisition cost"):
        CommerceSale(
            "bad-recovery",
            quantity=Decimal("1"),
            unit_sale_price=Decimal("100.00"),
            unit_acquisition_cost=Decimal("40.00"),
            inventory_recovery_credit=Decimal("40.01"),
        )


def test_zero_net_sales_has_no_fabricated_margin_ratio() -> None:
    result = calculate_commerce_result(
        sales=(
            CommerceSale(
                "zero-net",
                quantity=Decimal("1"),
                unit_sale_price=Decimal("100.00"),
                unit_acquisition_cost=Decimal("20.00"),
                discount_amount=Decimal("100.00"),
            ),
        ),
        operating_costs=(),
        rate_fees=(),
        fixed_fees=(),
    )
    assert result.net_sales == Decimal("0.00")
    assert result.contribution_profit == Decimal("-20.00")
    assert result.contribution_margin_ratio is None


def test_negative_contribution_is_preserved() -> None:
    result = calculate_commerce_result(
        sales=(
            CommerceSale(
                "loss",
                quantity=Decimal("1"),
                unit_sale_price=Decimal("50.00"),
                unit_acquisition_cost=Decimal("60.00"),
            ),
        ),
        operating_costs=(CommerceOperatingCost("pack", "packaging", Decimal("5.00")),),
        rate_fees=(),
        fixed_fees=(),
    )
    assert result.contribution_profit == Decimal("-15.00")


def test_rate_must_be_less_than_one() -> None:
    with pytest.raises(CommerceInputError, match="less than 1"):
        CommerceRateFee(
            "bad-rate",
            "payment_fee",
            base_amount=Decimal("100.00"),
            rate=Decimal("1.00"),
        )


def test_runtime_rejects_binary_float() -> None:
    with pytest.raises(CommerceInputError, match="must be Decimal"):
        CommerceOperatingCost(
            "float-cost",
            "fulfillment",
            1.5,  # type: ignore[arg-type]
        )


def test_duplicate_key_across_commerce_inputs_fails_closed() -> None:
    with pytest.raises(CommerceInputError, match="duplicate commerce line key"):
        calculate_commerce_result(
            sales=(
                CommerceSale(
                    "shared",
                    quantity=Decimal("1"),
                    unit_sale_price=Decimal("100.00"),
                    unit_acquisition_cost=Decimal("50.00"),
                ),
            ),
            operating_costs=(CommerceOperatingCost("shared", "packaging", Decimal("5.00")),),
            rate_fees=(),
            fixed_fees=(),
        )


def test_at_least_one_sale_line_is_required() -> None:
    with pytest.raises(CommerceInputError, match="at least one sale line"):
        calculate_commerce_result(
            sales=(),
            operating_costs=(),
            rate_fees=(),
            fixed_fees=(),
        )


def test_category_totals_are_deterministic() -> None:
    result = calculate_commerce_result(
        sales=(
            CommerceSale(
                "sale",
                quantity=Decimal("1"),
                unit_sale_price=Decimal("100.00"),
                unit_acquisition_cost=Decimal("20.00"),
            ),
        ),
        operating_costs=(
            CommerceOperatingCost("ads-2", "advertising", Decimal("3.00")),
            CommerceOperatingCost("pack", "packaging", Decimal("2.00")),
            CommerceOperatingCost("ads-1", "advertising", Decimal("4.00")),
        ),
        rate_fees=(
            CommerceRateFee(
                "pay",
                "payment_fee",
                base_amount=Decimal("100.00"),
                rate=Decimal("0.02"),
            ),
        ),
        fixed_fees=(CommerceFixedFee("market-fixed", "marketplace_commission", Decimal("1.00")),),
    )

    assert result.operating_category_costs == (
        ("advertising", Decimal("7.00")),
        ("packaging", Decimal("2.00")),
    )
    assert result.fee_category_costs == (
        ("marketplace_commission", Decimal("1.00")),
        ("payment_fee", Decimal("2.0000")),
    )


def test_snapshot_does_not_claim_inferred_marketplace_tax_or_return_rules() -> None:
    result = calculate_commerce_result(
        sales=(
            CommerceSale(
                "sale",
                quantity=Decimal("1"),
                unit_sale_price=Decimal("100.00"),
                unit_acquisition_cost=Decimal("20.00"),
            ),
        ),
        operating_costs=(),
        rate_fees=(),
        fixed_fees=(),
    )
    snapshot = build_commerce_snapshot(result)

    assert snapshot["marketplace_fee_schedule_inferred"] is False
    assert snapshot["payment_fee_schedule_inferred"] is False
    assert snapshot["return_probability_inferred"] is False
    assert snapshot["vat_treatment_applied"] is False
    assert snapshot["tax_policy_applied"] is False
    assert snapshot["inventory_valuation_policy_applied"] is False
