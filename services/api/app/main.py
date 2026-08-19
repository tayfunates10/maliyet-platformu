"""HTTP entry point for the Maliyet Platformu API."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import Body, Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import (
    AuthenticatedIdentity,
    AuthorizationError,
    require_calculation_write,
    resolve_actor_context,
)
from app.calculation_orchestration import CalculationOrchestrationError
from app.engine_registry import (
    EngineInputValidationError,
    EngineNotFoundError,
    describe_registered_engine,
    execute_and_record_registered_engine,
    list_registered_engines,
)
from app.http_dependencies import get_authenticated_identity, get_database_session
from app.models import Calculation
from app.tenancy import TenantResourceNotFound

SERVICE_NAME = "maliyet-calculation-api"
SERVICE_VERSION = "0.1.0"


class HealthResponse(BaseModel):
    """Stable health payload used by infrastructure probes."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"]
    service: str
    version: str


class EngineCatalogItem(BaseModel):
    """Public engine metadata without executable import/function details."""

    model_config = ConfigDict(frozen=True)

    key: str
    title: str
    engine_version: str
    execution_requires_trusted_actor: bool
    regulatory_rules_applied: bool


class EngineDetail(EngineCatalogItem):
    """Engine catalog item plus strict JSON input schema."""

    input_schema: dict[str, object]


class CalculationExecutionResponse(BaseModel):
    """Persisted execution provenance returned to an authorized tenant actor."""

    model_config = ConfigDict(frozen=True)

    calculation_id: UUID
    calculation_version_id: UUID
    version: int
    engine_key: str
    engine_version: str
    input_sha256: str
    ruleset_sha256: str
    output_sha256: str
    output_snapshot: dict[str, object]


app = FastAPI(
    title="Maliyet Platformu API",
    version=SERVICE_VERSION,
    description="Versioned API for costing, finance and integration capabilities.",
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Return a dependency-free process health signal."""

    return HealthResponse(status="ok", service=SERVICE_NAME, version=SERVICE_VERSION)


@app.get("/engines", response_model=list[EngineCatalogItem], tags=["engines"])
def engine_catalog() -> list[EngineCatalogItem]:
    """List allowlisted engines without exposing any execution target."""

    return [
        EngineCatalogItem(
            key=item.key,
            title=item.title,
            engine_version=item.engine_version,
            execution_requires_trusted_actor=item.execution_requires_trusted_actor,
            regulatory_rules_applied=item.regulatory_rules_applied,
        )
        for item in list_registered_engines()
    ]


@app.get("/engines/{engine_key}", response_model=EngineDetail, tags=["engines"])
def engine_detail(engine_key: str) -> EngineDetail:
    """Return the strict input schema for one allowlisted engine."""

    try:
        item = describe_registered_engine(engine_key)
    except EngineNotFoundError as exc:
        raise HTTPException(status_code=404, detail="engine not found") from exc
    return EngineDetail(
        key=item.key,
        title=item.title,
        engine_version=item.engine_version,
        execution_requires_trusted_actor=item.execution_requires_trusted_actor,
        regulatory_rules_applied=item.regulatory_rules_applied,
        input_schema=item.input_schema,
    )


@app.post(
    "/organizations/{organization_id}/calculations/{calculation_id}/execute/{engine_key}",
    response_model=CalculationExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["calculations"],
)
def execute_calculation_engine(
    organization_id: UUID,
    calculation_id: UUID,
    engine_key: str,
    payload: Annotated[dict[str, object], Body()],
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> CalculationExecutionResponse:
    """Execute and persist an allowlisted engine for an authenticated tenant writer."""

    try:
        actor = resolve_actor_context(
            session,
            identity=identity,
            organization_id=organization_id,
        )
        require_calculation_write(actor)
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="organization write access denied",
        ) from exc

    calculation = session.scalar(
        select(Calculation).where(
            Calculation.id == calculation_id,
            Calculation.organization_id == organization_id,
        )
    )
    if calculation is None:
        raise HTTPException(status_code=404, detail="calculation not found")
    if calculation.calculation_type != engine_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="engine does not match calculation type",
        )

    try:
        version, execution = execute_and_record_registered_engine(
            session,
            organization_id=actor.organization_id,
            calculation_id=calculation_id,
            created_by_user_id=actor.user_id,
            engine_key=engine_key,
            payload=payload,
        )
    except EngineNotFoundError as exc:
        raise HTTPException(status_code=404, detail="engine not found") from exc
    except EngineInputValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except TenantResourceNotFound as exc:
        raise HTTPException(status_code=404, detail="calculation not found") from exc
    except CalculationOrchestrationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if (
        version.input_sha256 is None
        or version.ruleset_sha256 is None
        or version.output_sha256 is None
    ):
        raise RuntimeError("new calculation version is missing provenance digests")

    return CalculationExecutionResponse(
        calculation_id=version.calculation_id,
        calculation_version_id=version.id,
        version=version.version,
        engine_key=execution.engine_key,
        engine_version=execution.engine_version,
        input_sha256=version.input_sha256,
        ruleset_sha256=version.ruleset_sha256,
        output_sha256=version.output_sha256,
        output_snapshot=execution.output_snapshot,
    )
