"""Strict HTTP-facing contract for accounting-to-tax-base reconciliation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TaxBaseAdjustmentInput(BaseModel):
    """One explicit accounting-to-tax-base adjustment line."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    key: str = Field(min_length=1, max_length=160)
    amount: str
    treatment: Literal["addition", "deduction"]


class TaxReconciliationInput(BaseModel):
    """JSON-safe inputs for explicit tax-base reconciliation only."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    accounting_profit_before_tax: str
    adjustments: list[TaxBaseAdjustmentInput] = Field(default_factory=list, max_length=500)
