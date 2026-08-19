"""Decimal and rule-driven regression tests for the calculation kernel."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.baseline_loader import load_tr_2026_baseline
from app.calculation_kernel import (
    CalculationInputError,
    CalculationRulePayloadError,
    calculate_flat_tax,
    calculate_progressive_tax,
    calculate_sgk_4a_full_month_premiums,
)
from app.rules_engine import resolve_rule


def resolved(db_session: Session, code: str):
    load_tr_2026_baseline(db_session)
    return resolve_rule(db_session, code=code, at_date=date(2026, 8, 19))


@pytest.mark.parametrize(
    ("taxable_base", "expected"),
    [
        ("0", "0.00"),
        ("190000.00", "28500.0000"),
        ("400000.00", "70500.0000"),
        ("1000000.00", "232500.0000"),
        ("5300000.00", "1737500.0000"),
        ("6000000.00", "2017500.0000"),
    ],
)
def test_2026_non_wage_income_tax_official_boundaries(
    db_session: Session,
    taxable_base: str,
    expected: str,
) -> None:
    rule = resolved(db_session, "TR.INCOME_TAX.NON_WAGE.TARIFF")
    result = calculate_progressive_tax(Decimal(taxable_base), rule)
    assert result.tax == Decimal(expected)


def test_income_tax_boundary_has_no_hidden_currency_rounding(db_session: Session) -> None:
    rule = resolved(db_session, "TR.INCOME_TAX.NON_WAGE.TARIFF")
    below = calculate_progressive_tax(Decimal("189999.99"), rule)
    boundary = calculate_progressive_tax(Decimal("190000.00"), rule)
    above = calculate_progressive_tax(Decimal("190000.01"), rule)

    assert below.tax == Decimal("28499.9985")
    assert boundary.tax == Decimal("28500.0000")
    assert above.tax == Decimal("28500.0020")


def test_wage_and_non_wage_tariffs_diverge_at_third_threshold(db_session: Session) -> None:
    wage_rule = resolved(db_session, "TR.INCOME_TAX.WAGE.TARIFF")
    non_wage_rule = resolved(db_session, "TR.INCOME_TAX.NON_WAGE.TARIFF")

    wage = calculate_progressive_tax(Decimal("1500000.00"), wage_rule)
    non_wage = calculate_progressive_tax(Decimal("1500000.00"), non_wage_rule)

    assert wage.tax == Decimal("367500.0000")
    assert non_wage.tax == Decimal("407500.0000")
    assert wage.marginal_rate == Decimal("0.27")
    assert non_wage.marginal_rate == Decimal("0.35")


def test_flat_tax_uses_resolved_rule_rate(db_session: Session) -> None:
    corporate = resolved(db_session, "TR.CORPORATE_TAX.GENERAL_RATE")
    provisional_income = resolved(db_session, "TR.PROVISIONAL_TAX.INCOME.GENERAL_RATE")

    assert calculate_flat_tax(Decimal("100000.00"), corporate).tax == Decimal("25000.0000")
    assert calculate_flat_tax(Decimal("100000.00"), provisional_income).tax == Decimal("15000.0000")


def test_tax_kernel_rejects_negative_base(db_session: Session) -> None:
    corporate = resolved(db_session, "TR.CORPORATE_TAX.GENERAL_RATE")
    with pytest.raises(CalculationInputError, match="non-negative"):
        calculate_flat_tax(Decimal("-0.01"), corporate)


def test_progressive_tariff_fails_closed_when_base_tax_continuity_is_corrupt(
    db_session: Session,
) -> None:
    rule = resolved(db_session, "TR.INCOME_TAX.NON_WAGE.TARIFF")
    bands = rule.version.payload["bands"]
    assert isinstance(bands, list)
    second = bands[1]
    assert isinstance(second, dict)
    second["base_tax"] = "28500.01"

    with pytest.raises(CalculationRulePayloadError, match="continuity"):
        calculate_progressive_tax(Decimal("200000.00"), rule)


def test_sgk_full_month_clamps_below_monthly_minimum(db_session: Session) -> None:
    limits = resolved(db_session, "TR.SGK.4A.PRIVATE.PEK_LIMITS")
    rates = resolved(db_session, "TR.SGK.4A.GENERAL.PREMIUM_RATES")
    result = calculate_sgk_4a_full_month_premiums(Decimal("20000.00"), limits, rates)

    assert result.premium_base == Decimal("33030.00")
    assert result.employee_premium == Decimal("4954.5000")
    assert result.employer_premium == Decimal("7844.625000")
    assert result.combined_premium == Decimal("12799.125000")


def test_sgk_full_month_clamps_above_monthly_maximum(db_session: Session) -> None:
    limits = resolved(db_session, "TR.SGK.4A.PRIVATE.PEK_LIMITS")
    rates = resolved(db_session, "TR.SGK.4A.GENERAL.PREMIUM_RATES")
    result = calculate_sgk_4a_full_month_premiums(Decimal("400000.00"), limits, rates)

    assert result.premium_base == Decimal("297270.00")
    assert result.employee_premium == Decimal("44590.5000")
    assert result.employer_premium == Decimal("70601.625000")
    assert result.combined_premium == Decimal("115192.125000")


def test_sgk_general_and_sgdp_profiles_use_different_rule_payloads(db_session: Session) -> None:
    limits = resolved(db_session, "TR.SGK.4A.PRIVATE.PEK_LIMITS")
    general = resolved(db_session, "TR.SGK.4A.GENERAL.PREMIUM_RATES")
    sgdp = resolved(db_session, "TR.SGK.4A.SGDP.PREMIUM_RATES")

    general_result = calculate_sgk_4a_full_month_premiums(Decimal("100000.00"), limits, general)
    sgdp_result = calculate_sgk_4a_full_month_premiums(Decimal("100000.00"), limits, sgdp)

    assert general_result.employer_premium == Decimal("23750.000000")
    assert general_result.employee_premium == Decimal("15000.0000")
    assert sgdp_result.employer_premium == Decimal("24750.0000")
    assert sgdp_result.employee_premium == Decimal("7500.0000")


def test_results_include_rule_provenance_snapshots(db_session: Session) -> None:
    corporate = resolved(db_session, "TR.CORPORATE_TAX.GENERAL_RATE")
    result = calculate_flat_tax(Decimal("100000.00"), corporate)

    assert result.rule_snapshot["code"] == "TR.CORPORATE_TAX.GENERAL_RATE"
    source = result.rule_snapshot["source"]
    assert isinstance(source, dict)
    assert source["canonical_url"] == (
        "https://www.gib.gov.tr/vergi-konulari/2_isletme_ve_girisimci/"
        "19_kurumlar_vergisinin_beyani/19"
    )
