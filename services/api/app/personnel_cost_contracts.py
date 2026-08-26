"""Strict HTTP-facing contract for regulated employer personnel cost execution."""

from pydantic import BaseModel, ConfigDict, Field


class EmployerCostLineInput(BaseModel):
    """One explicit employer-paid cost outside gross compensation and SGK."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    key: str = Field(min_length=1, max_length=160)
    amount: str


class PersonnelCostInput(BaseModel):
    """JSON-safe inputs for rule-resolved full-month employer personnel cost."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    at_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    gross_cash_compensation: str
    declared_monthly_earnings: str
    additional_employer_costs: list[EmployerCostLineInput] = Field(
        default_factory=list,
        max_length=500,
    )
