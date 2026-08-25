"""Explicit Decimal-only tax-base reconciliation and after-tax profitability.

Accounting profit is never assumed to equal a statutory taxable base. Callers
must provide each reconciliation adjustment explicitly, then bind the resulting
non-negative taxable base to an already rule-resolved tax result before current
tax expense can reduce accounting profit.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from typing import Literal

from app.calculation_kernel import FlatTaxResult, ProgressiveTaxResult

ENGINE_VERSION = "tax-reconciliation-v1"
DECIMAL_PRECISION = 76
MAX_INPUT_SIGNIFICANT_DIGITS = 38
MAX_INPUT_SCALE = 18
MAX_INPUT_INTEGER_DIGITS = 38
ZERO = Decimal("0")
ENGINE_CONTEXT = Context(
    prec=DECIMAL_PRECISION,
    rounding=ROUND_HALF_EVEN,
    Emin=-999_999,
    Emax=999_999,
    capitals=1,
    clamp=0,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)
AdjustmentTreatment = Literal["addition", "deduction"]
ResolvedTaxResult = FlatTaxResult | ProgressiveTaxResult


class TaxReconciliationInputError(ValueError):
    """Raised when reconciliation inputs cannot be processed safely."""


def _require_decimal(value: object, *, field: str, non_negative: bool = False) -> Decimal:
    if not isinstance(value, Decimal):
        raise TaxReconciliationInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise TaxReconciliationInputError(f"{field} must be finite")
    if non_negative and value < ZERO:
        raise TaxReconciliationInputError(f"{field} must be non-negative")

    decimal_tuple = value.as_tuple()
    exponent = decimal_tuple.exponent
    if not isinstance(exponent, int):
        raise TaxReconciliationInputError(f"{field} must be finite")
    significant_digits = len(decimal_tuple.digits)
    scale = max(-exponent, 0)
    integer_digits = max(value.copy_abs().adjusted() + 1, 0) if value != ZERO else 0
    if significant_digits > MAX_INPUT_SIGNIFICANT_DIGITS:
        raise TaxReconciliationInputError(
            f"{field} exceeds {MAX_INPUT_SIGNIFICANT_DIGITS} significant digits"
        )
    if scale > MAX_INPUT_SCALE:
        raise TaxReconciliationInputError(f"{field} exceeds scale {MAX_INPUT_SCALE}")
    if integer_digits > MAX_INPUT_INTEGER_DIGITS:
        raise TaxReconciliationInputError(
            f"{field} exceeds {MAX_INPUT_INTEGER_DIGITS} integer digits"
        )
    return value


@dataclass(frozen=True)
class TaxBaseAdjustment:
    """One explicit accounting-to-tax-base reconciliation line."""

    key: str
    amount: Decimal
    treatment: AdjustmentTreatment

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise TaxReconciliationInputError("adjustment.key must not be blank")
        _require_decimal(self.amount, field=f"adjustment[{self.key}].amount", non_negative=True)
        if self.treatment not in ("addition", "deduction"):
            raise TaxReconciliationInputError(
                f"adjustment[{self.key}].treatment must be addition or deduction"
            )


@dataclass(frozen=True)
class TaxBaseReconciliationResult:
    """Accounting profit reconciled to an explicit, unclamped taxable base."""

    accounting_profit_before_tax: Decimal
    additions_total: Decimal
    deductions_total: Decimal
    reconciled_taxable_base: Decimal
    adjustments: tuple[TaxBaseAdjustment, ...]


@dataclass(frozen=True)
class AfterTaxProfitResult:
    """Accounting profit after a rule-resolved current tax expense."""

    accounting_profit_before_tax: Decimal
    reconciled_taxable_base: Decimal
    current_tax_expense: Decimal
    accounting_profit_after_current_tax: Decimal
    tax_rule_snapshot: dict[str, object]


def reconcile_taxable_base(
    *,
    accounting_profit_before_tax: Decimal,
    adjustments: tuple[TaxBaseAdjustment, ...] = (),
) -> TaxBaseReconciliationResult:
    """Reconcile accounting profit without inferring tax-law adjustments.

    Negative reconciled bases are preserved rather than clamped. Their statutory
    treatment requires a separate explicit rule and cannot be inferred here.
    """

    accounting_profit = _require_decimal(
        accounting_profit_before_tax,
        field="accounting_profit_before_tax",
    )
    ordered = tuple(sorted(adjustments, key=lambda item: item.key))
    seen: set[str] = set()
    for adjustment in ordered:
        if adjustment.key in seen:
            raise TaxReconciliationInputError(f"duplicate adjustment key: {adjustment.key}")
        seen.add(adjustment.key)

    with localcontext(ENGINE_CONTEXT):
        additions = sum(
            (item.amount for item in ordered if item.treatment == "addition"),
            ZERO,
        )
        deductions = sum(
            (item.amount for item in ordered if item.treatment == "deduction"),
            ZERO,
        )
        taxable_base = accounting_profit + additions - deductions

    return TaxBaseReconciliationResult(
        accounting_profit_before_tax=accounting_profit,
        additions_total=additions,
        deductions_total=deductions,
        reconciled_taxable_base=taxable_base,
        adjustments=ordered,
    )


def calculate_after_tax_profit(
    reconciliation: TaxBaseReconciliationResult,
    tax_result: ResolvedTaxResult,
) -> AfterTaxProfitResult:
    """Apply only tax computed from the exact reconciled taxable base."""

    taxable_base = _require_decimal(
        reconciliation.reconciled_taxable_base,
        field="reconciliation.reconciled_taxable_base",
    )
    if taxable_base < ZERO:
        raise TaxReconciliationInputError(
            "negative reconciled taxable base requires an explicit statutory loss rule"
        )
    resolved_taxable_base = _require_decimal(
        tax_result.taxable_base,
        field="tax_result.taxable_base",
        non_negative=True,
    )
    current_tax = _require_decimal(
        tax_result.tax,
        field="tax_result.tax",
        non_negative=True,
    )
    if resolved_taxable_base != taxable_base:
        raise TaxReconciliationInputError(
            "tax_result.taxable_base must equal reconciled_taxable_base"
        )

    with localcontext(ENGINE_CONTEXT):
        after_tax = reconciliation.accounting_profit_before_tax - current_tax

    return AfterTaxProfitResult(
        accounting_profit_before_tax=reconciliation.accounting_profit_before_tax,
        reconciled_taxable_base=taxable_base,
        current_tax_expense=current_tax,
        accounting_profit_after_current_tax=after_tax,
        tax_rule_snapshot=dict(tax_result.rule_snapshot),
    )


def build_tax_reconciliation_snapshot(
    reconciliation: TaxBaseReconciliationResult,
    after_tax: AfterTaxProfitResult | None = None,
) -> dict[str, object]:
    """Serialize reconciliation provenance without inventing tax treatment."""

    snapshot: dict[str, object] = {
        "engine_version": ENGINE_VERSION,
        "decimal_policy": {
            "precision": DECIMAL_PRECISION,
            "rounding": "ROUND_HALF_EVEN",
            "emin": ENGINE_CONTEXT.Emin,
            "emax": ENGINE_CONTEXT.Emax,
            "max_input_significant_digits": MAX_INPUT_SIGNIFICANT_DIGITS,
            "max_input_scale": MAX_INPUT_SCALE,
            "max_input_integer_digits": MAX_INPUT_INTEGER_DIGITS,
            "implicit_currency_rounding": False,
        },
        "accounting_profit_before_tax": str(reconciliation.accounting_profit_before_tax),
        "additions_total": str(reconciliation.additions_total),
        "deductions_total": str(reconciliation.deductions_total),
        "reconciled_taxable_base": str(reconciliation.reconciled_taxable_base),
        "adjustments": [
            {
                "key": item.key,
                "amount": str(item.amount),
                "treatment": item.treatment,
            }
            for item in reconciliation.adjustments
        ],
        "taxable_base_inferred_from_accounting_profit": False,
        "negative_tax_base_treatment_inferred": False,
    }
    if after_tax is not None:
        if (
            after_tax.reconciled_taxable_base != reconciliation.reconciled_taxable_base
            or after_tax.accounting_profit_before_tax != reconciliation.accounting_profit_before_tax
        ):
            raise TaxReconciliationInputError("after_tax result does not belong to reconciliation")
        snapshot["current_tax_expense"] = str(after_tax.current_tax_expense)
        snapshot["accounting_profit_after_current_tax"] = str(
            after_tax.accounting_profit_after_current_tax
        )
        snapshot["tax_rule_snapshot"] = after_tax.tax_rule_snapshot
    return snapshot
