"""Regression tests for tourism package management economics."""

from decimal import Decimal

import pytest

from app.tourism_engine import (
    TourismChannelSale,
    TourismComponentCost,
    TourismInputError,
    TourismPackagePlan,
    as_core_direct_cost,
    build_tourism_snapshot,
    calculate_tourism_package,
)


def test_tourism_package_reconciles_participants_channels_and_components() -> None:
    result = calculate_tourism_package(
        plan=TourismPackagePlan(participant_count=20, currency="TRY"),
        channel_sales=(
            TourismChannelSale(
                "direct",
                participant_count=12,
                gross_revenue=Decimal("120000.00"),
                revenue_reduction_amount=Decimal("5000.00"),
            ),
            TourismChannelSale(
                "agency",
                participant_count=8,
                gross_revenue=Decimal("88000.00"),
                revenue_reduction_amount=Decimal("3000.00"),
                commission_base_amount=Decimal("85000.00"),
                commission_rate=Decimal("0.10"),
                fixed_channel_fee=Decimal("500.00"),
            ),
        ),
        components=(
            TourismComponentCost(
                "hotel",
                "accommodation",
                "per_participant",
                Decimal("2500.00"),
            ),
            TourismComponentCost(
                "meal",
                "meal",
                "per_participant",
                Decimal("800.00"),
            ),
            TourismComponentCost(
                "tickets",
                "ticket",
                "per_participant",
                Decimal("400.00"),
            ),
            TourismComponentCost(
                "insurance",
                "insurance",
                "per_participant",
                Decimal("100.00"),
            ),
            TourismComponentCost(
                "coach",
                "transportation",
                "fixed_package",
                Decimal("20000.00"),
            ),
            TourismComponentCost(
                "guide",
                "guide",
                "fixed_package",
                Decimal("6000.00"),
            ),
            TourismComponentCost(
                "transfer",
                "transfer",
                "fixed_package",
                Decimal("4000.00"),
            ),
        ),
    )

    assert result.participant_count == 20
    assert result.currency == "TRY"
    assert result.gross_revenue == Decimal("208000.00")
    assert result.revenue_reduction_amount == Decimal("8000.00")
    assert result.net_revenue_before_channel_fee == Decimal("200000.00")
    assert result.percentage_channel_fee == Decimal("8500.0000")
    assert result.fixed_channel_fee == Decimal("500.00")
    assert result.total_channel_fee == Decimal("9000.0000")
    assert result.net_revenue_after_channel_fee == Decimal("191000.0000")
    assert result.per_participant_component_cost == Decimal("76000.00")
    assert result.fixed_package_component_cost == Decimal("30000.00")
    assert result.total_package_cost == Decimal("106000.00")
    assert result.cost_per_participant == Decimal("5300.00")
    assert result.net_revenue_per_participant == Decimal("9550.0000")
    assert result.package_contribution == Decimal("85000.0000")
    assert result.contribution_per_participant == Decimal("4250.0000")
    assert result.contribution_margin_ratio == Decimal("85000.0000") / Decimal("191000.0000")


def test_channel_commission_uses_explicit_base() -> None:
    sale = TourismChannelSale(
        "agency",
        participant_count=1,
        gross_revenue=Decimal("1000.00"),
        commission_base_amount=Decimal("500.00"),
        commission_rate=Decimal("0.10"),
    )
    assert sale.percentage_channel_fee == Decimal("50.0000")


def test_channel_participants_must_equal_package_participants() -> None:
    with pytest.raises(TourismInputError, match="must equal package participant_count"):
        calculate_tourism_package(
            plan=TourismPackagePlan(10, "TRY"),
            channel_sales=(TourismChannelSale("direct", 9, Decimal("9000.00")),),
            components=(),
        )


def test_participant_count_must_be_positive_integer() -> None:
    with pytest.raises(TourismInputError, match="positive integer"):
        TourismPackagePlan(0, "TRY")


def test_currency_must_not_be_blank() -> None:
    with pytest.raises(TourismInputError, match="must not be blank"):
        TourismPackagePlan(1, "   ")


def test_revenue_reduction_cannot_exceed_gross() -> None:
    with pytest.raises(TourismInputError, match="cannot exceed gross revenue"):
        TourismChannelSale(
            "bad",
            1,
            Decimal("100.00"),
            revenue_reduction_amount=Decimal("100.01"),
        )


def test_commission_rate_must_be_less_than_one() -> None:
    with pytest.raises(TourismInputError, match="less than 1"):
        TourismChannelSale(
            "bad-rate",
            1,
            Decimal("100.00"),
            commission_rate=Decimal("1.00"),
        )


def test_runtime_rejects_binary_float_component_amount() -> None:
    with pytest.raises(TourismInputError, match="must be Decimal"):
        TourismComponentCost(
            "bad",
            "meal",
            "per_participant",
            1.5,  # type: ignore[arg-type]
        )


def test_duplicate_key_across_channel_and_component_fails_closed() -> None:
    with pytest.raises(TourismInputError, match="duplicate tourism line key"):
        calculate_tourism_package(
            plan=TourismPackagePlan(1, "TRY"),
            channel_sales=(TourismChannelSale("shared", 1, Decimal("100.00")),),
            components=(
                TourismComponentCost("shared", "meal", "per_participant", Decimal("10.00")),
            ),
        )


def test_component_category_totals_are_deterministic() -> None:
    result = calculate_tourism_package(
        plan=TourismPackagePlan(2, "EUR"),
        channel_sales=(TourismChannelSale("direct", 2, Decimal("1000.00")),),
        components=(
            TourismComponentCost("meal-b", "meal", "per_participant", Decimal("20.00")),
            TourismComponentCost("guide", "guide", "fixed_package", Decimal("100.00")),
            TourismComponentCost("meal-a", "meal", "per_participant", Decimal("30.00")),
        ),
    )

    assert result.component_category_totals == (
        ("guide", Decimal("100.00")),
        ("meal", Decimal("100.00")),
    )


def test_tourism_package_cost_bridges_to_core_direct_cost() -> None:
    result = calculate_tourism_package(
        plan=TourismPackagePlan(1, "TRY"),
        channel_sales=(TourismChannelSale("direct", 1, Decimal("100.00")),),
        components=(TourismComponentCost("meal", "meal", "per_participant", Decimal("25.00")),),
    )
    line = as_core_direct_cost(result, key="tour-42")

    assert line.key == "tour-42"
    assert line.amount == Decimal("25.00")


def test_snapshot_does_not_claim_fx_tax_or_legal_policies() -> None:
    result = calculate_tourism_package(
        plan=TourismPackagePlan(1, "USD"),
        channel_sales=(TourismChannelSale("direct", 1, Decimal("100.00")),),
        components=(),
    )
    snapshot = build_tourism_snapshot(result)

    assert snapshot["currency"] == "USD"
    assert snapshot["fx_conversion_applied"] is False
    assert snapshot["fx_rate_inferred"] is False
    assert snapshot["agency_fee_schedule_inferred"] is False
    assert snapshot["tourism_tax_policy_applied"] is False
    assert snapshot["vat_treatment_applied"] is False
    assert snapshot["travel_package_legal_policy_applied"] is False
