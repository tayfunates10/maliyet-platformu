"""Regression tests for explicit tax-base reconciliation and after-tax profit."""

from decimal import Decimal, Inexact, getcontext, setcontext

import pytest

from app.calculation_kernel import FlatTaxResult, ProgressiveTaxResult
from app.tax_reconciliation import (
    TaxBaseAdjustment,
    TaxReconciliationInputError,
    build_tax_reconciliation_snapshot,
    calculate_after_tax_profit,
    reconcile_taxable_base,
)


def _flat_tax(taxable_base: Decimal, tax: Decimal) -> FlatTaxResult:
    return FlatTaxResult(
        taxable_base=taxable_base,
        rate=Decimal("0.20"),
        tax=tax,
        rule_snapshot={"rule_key": "corporate-tax", "version": "2026-01"},
    )


def test_reconciliation_uses_explicit_additions_and_deductions() -> None:
    result = reconcile_taxable_base(
        accounting_profit_before_tax=Decimal("100000.00"),
        adjustments=(
            TaxBaseAdjustment("allowance", Decimal("5000.00"), "deduction"),
            TaxBaseAdjustment("non-deductible", Decimal("10000.00"), "addition"),
        ),
    )

    assert result.additions_total == Decimal("10000.00")
    assert result.deductions_total == Decimal("5000.00")
    assert result.reconciled_taxable_base == Decimal("105000.00")
    assert tuple(item.key for item in result.adjustments) == (
        "allowance",
        "non-deductible",
    )


def test_after_tax_profit_requires_tax_result_for_exact_reconciled_base() -> None:
    reconciliation = reconcile_taxable_base(
        accounting_profit_before_tax=Decimal("100000.00"),
        adjustments=(TaxBaseAdjustment("addition", Decimal("5000.00"), "addition"),),
    )
    result = calculate_after_tax_profit(
        reconciliation,
        _flat_tax(Decimal("105000.00"), Decimal("21000.00")),
    )

    assert result.current_tax_expense == Decimal("21000.00")
    assert result.accounting_profit_after_current_tax == Decimal("79000.00")
    assert result.tax_rule_snapshot == {
        "rule_key": "corporate-tax",
        "version": "2026-01",
    }


def test_tax_result_with_different_base_fails_closed() -> None:
    reconciliation = reconcile_taxable_base(
        accounting_profit_before_tax=Decimal("100000.00"),
    )
    with pytest.raises(TaxReconciliationInputError, match="must equal"):
        calculate_after_tax_profit(
            reconciliation,
            _flat_tax(Decimal("99999.99"), Decimal("20000.00")),
        )


def test_negative_reconciled_base_is_preserved_but_not_given_implicit_tax_treatment() -> None:
    reconciliation = reconcile_taxable_base(
        accounting_profit_before_tax=Decimal("-10000.00"),
        adjustments=(TaxBaseAdjustment("addition", Decimal("1000.00"), "addition"),),
    )

    assert reconciliation.reconciled_taxable_base == Decimal("-9000.00")
    with pytest.raises(TaxReconciliationInputError, match="statutory loss rule"):
        calculate_after_tax_profit(
            reconciliation,
            _flat_tax(Decimal("0"), Decimal("0")),
        )


def test_progressive_tax_result_is_accepted_when_base_matches() -> None:
    reconciliation = reconcile_taxable_base(
        accounting_profit_before_tax=Decimal("50000.00"),
    )
    tax_result = ProgressiveTaxResult(
        taxable_base=Decimal("50000.00"),
        tax=Decimal("7500.00"),
        marginal_rate=Decimal("0.20"),
        bracket_lower_bound=Decimal("30000.00"),
        bracket_upper_bound=Decimal("80000.00"),
        rule_snapshot={"rule_key": "progressive-tax", "version": "2026-01"},
    )

    result = calculate_after_tax_profit(reconciliation, tax_result)
    assert result.accounting_profit_after_current_tax == Decimal("42500.00")


def test_duplicate_adjustments_and_binary_float_fail_closed() -> None:
    with pytest.raises(TaxReconciliationInputError, match="duplicate adjustment key"):
        reconcile_taxable_base(
            accounting_profit_before_tax=Decimal("1000.00"),
            adjustments=(
                TaxBaseAdjustment("same", Decimal("10.00"), "addition"),
                TaxBaseAdjustment("same", Decimal("5.00"), "deduction"),
            ),
        )

    with pytest.raises(TaxReconciliationInputError, match="must be Decimal"):
        reconcile_taxable_base(
            accounting_profit_before_tax=1000.0,  # type: ignore[arg-type]
        )


def test_reconciliation_is_independent_of_caller_decimal_context() -> None:
    original_context = getcontext().copy()
    try:
        getcontext().prec = 5
        getcontext().Emax = 5
        getcontext().traps[Inexact] = True
        constrained = reconcile_taxable_base(
            accounting_profit_before_tax=Decimal("100000.01"),
            adjustments=(TaxBaseAdjustment("add", Decimal("0.02"), "addition"),),
        )

        setcontext(original_context.copy())
        getcontext().prec = 50
        unconstrained = reconcile_taxable_base(
            accounting_profit_before_tax=Decimal("100000.01"),
            adjustments=(TaxBaseAdjustment("add", Decimal("0.02"), "addition"),),
        )
    finally:
        setcontext(original_context)

    assert constrained == unconstrained
    assert constrained.reconciled_taxable_base == Decimal("100000.03")


def test_snapshot_records_explicit_reconciliation_and_tax_provenance() -> None:
    reconciliation = reconcile_taxable_base(
        accounting_profit_before_tax=Decimal("100000.00"),
        adjustments=(TaxBaseAdjustment("add", Decimal("5000.00"), "addition"),),
    )
    after_tax = calculate_after_tax_profit(
        reconciliation,
        _flat_tax(Decimal("105000.00"), Decimal("21000.00")),
    )
    snapshot = build_tax_reconciliation_snapshot(reconciliation, after_tax)

    assert snapshot["reconciled_taxable_base"] == "105000.00"
    assert snapshot["current_tax_expense"] == "21000.00"
    assert snapshot["accounting_profit_after_current_tax"] == "79000.00"
    assert snapshot["taxable_base_inferred_from_accounting_profit"] is False
    assert snapshot["negative_tax_base_treatment_inferred"] is False
    assert snapshot["tax_rule_snapshot"] == {
        "rule_key": "corporate-tax",
        "version": "2026-01",
    }


def test_snapshot_rejects_after_tax_result_from_different_reconciliation() -> None:
    first = reconcile_taxable_base(
        accounting_profit_before_tax=Decimal("100000.00"),
        adjustments=(TaxBaseAdjustment("add", Decimal("5000.00"), "addition"),),
    )
    second = reconcile_taxable_base(
        accounting_profit_before_tax=Decimal("90000.00"),
        adjustments=(TaxBaseAdjustment("add", Decimal("15000.00"), "addition"),),
    )
    second_after_tax = calculate_after_tax_profit(
        second,
        _flat_tax(Decimal("105000.00"), Decimal("21000.00")),
    )

    with pytest.raises(TaxReconciliationInputError, match="does not belong"):
        build_tax_reconciliation_snapshot(first, second_after_tax)
