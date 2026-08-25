"""Strict HTTP-facing contract for accounting asset depreciation execution."""

from pydantic import BaseModel, ConfigDict, Field


class AssetDepreciationInput(BaseModel):
    """JSON-safe explicit straight-line book depreciation inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    asset_key: str = Field(min_length=1, max_length=160)
    acquisition_cost: str
    residual_value: str
    useful_life_months: int = Field(gt=0, le=1_000_000)
    elapsed_months: int = Field(ge=0, le=1_000_000)
