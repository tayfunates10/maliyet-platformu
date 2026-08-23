"""Authenticated tenant HTTP adapter for investment and scenario decision analysis."""

from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from sqlalchemy.orm import Session

from app.auth_context import AuthenticatedIdentity, AuthorizationError, resolve_actor_context
from app.http_dependencies import get_authenticated_identity, get_database_session
from app.investment_scenario_engine import (
    InvestmentMetricInputs,
    InvestmentScenarioInputError,
    ScenarioCase,
    build_investment_scenario_snapshot,
    calculate_investment_metrics,
    calculate_scenarios,
)

router = APIRouter(prefix="/organizations/{organization_id}/decision-analysis", tags=["decision-analysis"])


class ScenarioRequest(BaseModel):
    """One explicit scenario; values stay strings across the JSON boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)

    key: Literal["pessimistic", "normal", "optimistic"]
    revenue: StrictStr = Field(min_length=1, max_length=120)
    costs: StrictStr = Field(min_length=1, max_length=120)


class InvestmentScenarioRequest(BaseModel):
    """Strict Decimal-string request for one tenant-scoped decision analysis."""

    model_config = ConfigDict(extra="forbid", strict=True)

    initial_investment: StrictStr = Field(min_length=1, max_length=120)
    net_return: StrictStr = Field(min_length=1, max_length=120)
    equity: StrictStr = Field(min_length=1, max_length=120)
    net_income: StrictStr = Field(min_length=1, max_length=120)
    invested_capital: StrictStr = Field(min_length=1, max_length=120)
    net_operating_profit_after_tax: StrictStr = Field(min_length=1, max_length=120)
    scenarios: list[ScenarioRequest] = Field(min_length=3, max_length=3)


class InvestmentScenarioResponse(BaseModel):
    """Typed response envelope containing the engine's deterministic snapshot."""

    model_config = ConfigDict(frozen=True)

    snapshot: dict[str, object]


def _decimal(value: str, *, field: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field} must be a valid decimal string",
        ) from exc
    if not result.is_finite():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field} must be finite",
        )
    return result


def _require_membership(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
) -> None:
    try:
        resolve_actor_context(session, identity=identity, organization_id=organization_id)
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="organization access denied",
        ) from exc


@router.post(
    "/investment-scenarios",
    response_model=InvestmentScenarioResponse,
)
def calculate_investment_scenario_analysis(
    organization_id: UUID,
    payload: InvestmentScenarioRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> InvestmentScenarioResponse:
    """Calculate tenant-private ROI/ROE/ROIC and explicit three-case scenarios."""

    _require_membership(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    try:
        metrics = calculate_investment_metrics(
            InvestmentMetricInputs(
                initial_investment=_decimal(payload.initial_investment, field="initial_investment"),
                net_return=_decimal(payload.net_return, field="net_return"),
                equity=_decimal(payload.equity, field="equity"),
                net_income=_decimal(payload.net_income, field="net_income"),
                invested_capital=_decimal(payload.invested_capital, field="invested_capital"),
                net_operating_profit_after_tax=_decimal(
                    payload.net_operating_profit_after_tax,
                    field="net_operating_profit_after_tax",
                ),
            )
        )
        scenarios = calculate_scenarios(
            [
                ScenarioCase(
                    key=item.key,
                    revenue=_decimal(item.revenue, field=f"scenario[{item.key}].revenue"),
                    costs=_decimal(item.costs, field=f"scenario[{item.key}].costs"),
                )
                for item in payload.scenarios
            ]
        )
        snapshot = build_investment_scenario_snapshot(metrics=metrics, scenarios=scenarios)
    except InvestmentScenarioInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return InvestmentScenarioResponse(snapshot=snapshot)
