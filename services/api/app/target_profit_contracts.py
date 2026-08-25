"""Strict HTTP-facing contract for target-profit pricing execution."""

from pydantic import BaseModel, ConfigDict


class TargetProfitPricingInput(BaseModel):
    """JSON-safe target-profit pricing input.

    All continuous and monetary values remain strings at the transport boundary
    so they cannot pass through binary floating point before Decimal parsing.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    variable_cost_per_unit: str
    fixed_costs: str
    target_profit: str
    expected_units: str
