"""Strict HTTP-facing contract for regulated employer personnel cost execution."""

from pydantic import BaseModel, ConfigDict, Field

DECIMAL_MONEY_PATTERN = r"^\d{1,38}(?:\.\d{1,18})?$"


class EmployerCostLineInput(BaseModel):
    """One explicit employer-paid cost outside gross compensation and SGK."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    key: str = Field(min_length=1, max_length=160)
    amount: str = Field(pattern=DECIMAL_MONEY_PATTERN)


class PersonnelCostInput(BaseModel):
    """JSON-safe inputs for rule-resolved full-month employer personnel cost."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    at_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    gross_cash_compensation: str = Field(pattern=DECIMAL_MONEY_PATTERN)
    declared_monthly_earnings: str = Field(pattern=DECIMAL_MONEY_PATTERN)
    additional_employer_costs: list[EmployerCostLineInput] = Field(
        default_factory=list,
        max_length=500,
    )
