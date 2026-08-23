"""Authenticated tenant HTTP adapter for investment and scenario decision analysis."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import (
    ActorContext,
    AuthenticatedIdentity,
    AuthorizationError,
    resolve_actor_context,
)
from app.decision_analysis_models import DecisionAnalysisArtifact
from app.decision_analysis_persistence import (
    DecisionAnalysisIntegrityError,
    load_decision_analysis,
    record_decision_analysis,
)
from app.http_dependencies import get_authenticated_identity, get_database_session
from app.investment_scenario_engine import (
    InvestmentMetricInputs,
    InvestmentScenarioInputError,
    ScenarioCase,
    build_investment_scenario_snapshot,
    calculate_investment_metrics,
    calculate_scenarios,
)
from app.tenancy import TenantResourceNotFound

router = APIRouter(prefix="/{organization_id}/decision-analysis", tags=["decision-analysis"])

MAX_DECIMAL_ADJUSTED_EXPONENT = 120
MAX_DECIMAL_DIGITS = 120


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
    """Persisted immutable artifact plus deterministic engine snapshot."""

    model_config = ConfigDict(frozen=True)

    artifact_id: UUID
    input_sha256: str
    output_sha256: str
    created_at: datetime
    snapshot: dict[str, object]


class DecisionAnalysisArtifactSummary(BaseModel):
    """Bounded history-list projection without replaying current engine state."""

    model_config = ConfigDict(frozen=True)

    artifact_id: UUID
    engine_version: str
    input_sha256: str
    output_sha256: str
    created_at: datetime


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
    decimal_tuple = result.as_tuple()
    if len(decimal_tuple.digits) > MAX_DECIMAL_DIGITS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field} exceeds supported decimal precision",
        )
    if result != 0 and abs(result.adjusted()) > MAX_DECIMAL_ADJUSTED_EXPONENT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field} exceeds supported decimal exponent range",
        )
    return result


def _require_membership(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
) -> ActorContext:
    try:
        return resolve_actor_context(
            session,
            identity=identity,
            organization_id=organization_id,
        )
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
    """Calculate and append one tenant-private immutable decision-analysis artifact."""

    actor = _require_membership(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    try:
        metric_inputs = InvestmentMetricInputs(
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
        scenario_inputs = [
            ScenarioCase(
                key=item.key,
                revenue=_decimal(item.revenue, field=f"scenario[{item.key}].revenue"),
                costs=_decimal(item.costs, field=f"scenario[{item.key}].costs"),
            )
            for item in payload.scenarios
        ]
        metrics = calculate_investment_metrics(metric_inputs)
        scenarios = calculate_scenarios(scenario_inputs)
        snapshot = build_investment_scenario_snapshot(metrics=metrics, scenarios=scenarios)
        input_snapshot: dict[str, object] = {
            "initial_investment": str(metric_inputs.initial_investment),
            "net_return": str(metric_inputs.net_return),
            "equity": str(metric_inputs.equity),
            "net_income": str(metric_inputs.net_income),
            "invested_capital": str(metric_inputs.invested_capital),
            "net_operating_profit_after_tax": str(metric_inputs.net_operating_profit_after_tax),
            "scenarios": [
                {
                    "key": item.key,
                    "revenue": str(item.revenue),
                    "costs": str(item.costs),
                }
                for item in scenario_inputs
            ],
        }
        snapshot["inputs"] = input_snapshot
    except InvestmentScenarioInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    engine_version = snapshot.get("engine_version")
    if not isinstance(engine_version, str):
        raise RuntimeError("decision analysis engine snapshot missing engine_version")
    artifact = record_decision_analysis(
        session,
        organization_id=organization_id,
        created_by_user_id=actor.user_id,
        engine_version=engine_version,
        input_snapshot=input_snapshot,
        output_snapshot=snapshot,
    )
    return InvestmentScenarioResponse(
        artifact_id=artifact.id,
        input_sha256=artifact.input_sha256,
        output_sha256=artifact.output_sha256,
        created_at=artifact.created_at,
        snapshot=artifact.output_snapshot,
    )


@router.get(
    "/investment-scenarios",
    response_model=list[DecisionAnalysisArtifactSummary],
)
def list_investment_scenario_analyses(
    organization_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DecisionAnalysisArtifactSummary]:
    """List bounded tenant artifact metadata without recalculation."""

    _require_membership(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    artifacts = session.scalars(
        select(DecisionAnalysisArtifact)
        .where(DecisionAnalysisArtifact.organization_id == organization_id)
        .order_by(
            DecisionAnalysisArtifact.created_at.desc(),
            DecisionAnalysisArtifact.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        DecisionAnalysisArtifactSummary(
            artifact_id=artifact.id,
            engine_version=artifact.engine_version,
            input_sha256=artifact.input_sha256,
            output_sha256=artifact.output_sha256,
            created_at=artifact.created_at,
        )
        for artifact in artifacts
    ]


@router.get(
    "/investment-scenarios/{artifact_id}",
    response_model=InvestmentScenarioResponse,
)
def get_investment_scenario_analysis(
    organization_id: UUID,
    artifact_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> InvestmentScenarioResponse:
    """Return a verified historical artifact without executing the current engine."""

    _require_membership(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    try:
        replay = load_decision_analysis(
            session,
            organization_id=organization_id,
            artifact_id=artifact_id,
        )
    except TenantResourceNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="analysis not found") from exc
    except DecisionAnalysisIntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="analysis integrity check failed",
        ) from exc
    return InvestmentScenarioResponse(
        artifact_id=replay.artifact_id,
        input_sha256=replay.input_sha256,
        output_sha256=replay.output_sha256,
        created_at=replay.created_at,
        snapshot=replay.output_snapshot,
    )
