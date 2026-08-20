"""HTTP entry point for the Maliyet Platformu API."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import (
    ActorContext,
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
from app.models import AuditEvent, Calculation, CalculationVersion
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


class CalculationCreateRequest(BaseModel):
    """Strict request for one tenant-owned logical calculation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=240)
    calculation_type: str = Field(min_length=1, max_length=80)


class CalculationResponse(BaseModel):
    """Tenant-safe logical calculation metadata."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    name: str
    calculation_type: str
    created_at: datetime
    updated_at: datetime


class CalculationVersionResponse(BaseModel):
    """Immutable calculation version snapshot visible to an authorized tenant member."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    calculation_id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    version: int
    engine_key: str | None
    engine_version: str
    input_snapshot: dict[str, object]
    input_sha256: str | None
    ruleset_snapshot: dict[str, object]
    ruleset_sha256: str | None
    output_snapshot: dict[str, object]
    output_sha256: str | None
    created_at: datetime


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


def _actor_for_organization(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    write: bool = False,
) -> ActorContext:
    """Resolve one authenticated organization member and optionally require write access."""

    try:
        actor = resolve_actor_context(
            session,
            identity=identity,
            organization_id=organization_id,
        )
        if write:
            require_calculation_write(actor)
    except AuthorizationError as exc:
        detail = "organization write access denied" if write else "organization access denied"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail) from exc
    return actor


def _tenant_calculation_or_404(
    session: Session,
    *,
    organization_id: UUID,
    calculation_id: UUID,
) -> Calculation:
    calculation = session.scalar(
        select(Calculation).where(
            Calculation.id == calculation_id,
            Calculation.organization_id == organization_id,
        )
    )
    if calculation is None:
        raise HTTPException(status_code=404, detail="calculation not found")
    return calculation


def _calculation_response(calculation: Calculation) -> CalculationResponse:
    return CalculationResponse(
        id=calculation.id,
        organization_id=calculation.organization_id,
        created_by_user_id=calculation.created_by_user_id,
        name=calculation.name,
        calculation_type=calculation.calculation_type,
        created_at=calculation.created_at,
        updated_at=calculation.updated_at,
    )


def _calculation_version_response(version: CalculationVersion) -> CalculationVersionResponse:
    return CalculationVersionResponse(
        id=version.id,
        calculation_id=version.calculation_id,
        organization_id=version.organization_id,
        created_by_user_id=version.created_by_user_id,
        version=version.version,
        engine_key=version.engine_key,
        engine_version=version.engine_version,
        input_snapshot=version.input_snapshot,
        input_sha256=version.input_sha256,
        ruleset_snapshot=version.ruleset_snapshot,
        ruleset_sha256=version.ruleset_sha256,
        output_snapshot=version.output_snapshot,
        output_sha256=version.output_sha256,
        created_at=version.created_at,
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
    "/organizations/{organization_id}/calculations",
    response_model=CalculationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["calculations"],
)
def create_calculation(
    organization_id: UUID,
    payload: CalculationCreateRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> CalculationResponse:
    """Create one tenant-owned calculation using the authenticated actor as creator."""

    actor = _actor_for_organization(
        session,
        identity=identity,
        organization_id=organization_id,
        write=True,
    )
    try:
        describe_registered_engine(payload.calculation_type)
    except EngineNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="unsupported calculation type",
        ) from exc

    calculation = Calculation(
        organization_id=organization_id,
        created_by_user_id=actor.user_id,
        name=payload.name,
        calculation_type=payload.calculation_type,
    )
    session.add(calculation)
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor.user_id,
            event_type="calculation.created",
            entity_type="calculation",
            entity_id=calculation.id,
            payload={"calculation_type": calculation.calculation_type},
        )
    )
    session.flush()
    return _calculation_response(calculation)


@app.get(
    "/organizations/{organization_id}/calculations",
    response_model=list[CalculationResponse],
    tags=["calculations"],
)
def list_calculations(
    organization_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CalculationResponse]:
    """List calculations only inside the authenticated member's requested organization."""

    _actor_for_organization(session, identity=identity, organization_id=organization_id)
    calculations = session.scalars(
        select(Calculation)
        .where(Calculation.organization_id == organization_id)
        .order_by(Calculation.created_at.desc(), Calculation.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [_calculation_response(calculation) for calculation in calculations]


@app.get(
    "/organizations/{organization_id}/calculations/{calculation_id}",
    response_model=CalculationResponse,
    tags=["calculations"],
)
def get_calculation(
    organization_id: UUID,
    calculation_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> CalculationResponse:
    """Return one calculation only after tenant membership is established."""

    _actor_for_organization(session, identity=identity, organization_id=organization_id)
    return _calculation_response(
        _tenant_calculation_or_404(
            session,
            organization_id=organization_id,
            calculation_id=calculation_id,
        )
    )


@app.get(
    "/organizations/{organization_id}/calculations/{calculation_id}/versions",
    response_model=list[CalculationVersionResponse],
    tags=["calculations"],
)
def list_calculation_versions(
    organization_id: UUID,
    calculation_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CalculationVersionResponse]:
    """Return immutable version history for one tenant calculation."""

    _actor_for_organization(session, identity=identity, organization_id=organization_id)
    _tenant_calculation_or_404(
        session,
        organization_id=organization_id,
        calculation_id=calculation_id,
    )
    versions = session.scalars(
        select(CalculationVersion)
        .where(
            CalculationVersion.organization_id == organization_id,
            CalculationVersion.calculation_id == calculation_id,
        )
        .order_by(CalculationVersion.version.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [_calculation_version_response(version) for version in versions]


@app.get(
    "/organizations/{organization_id}/calculations/{calculation_id}/versions/{version_number}",
    response_model=CalculationVersionResponse,
    tags=["calculations"],
)
def get_calculation_version(
    organization_id: UUID,
    calculation_id: UUID,
    version_number: int,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> CalculationVersionResponse:
    """Return one immutable version snapshot by its monotonic version number."""

    _actor_for_organization(session, identity=identity, organization_id=organization_id)
    _tenant_calculation_or_404(
        session,
        organization_id=organization_id,
        calculation_id=calculation_id,
    )
    version = session.scalar(
        select(CalculationVersion).where(
            CalculationVersion.organization_id == organization_id,
            CalculationVersion.calculation_id == calculation_id,
            CalculationVersion.version == version_number,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="calculation version not found")
    return _calculation_version_response(version)


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

    actor = _actor_for_organization(
        session,
        identity=identity,
        organization_id=organization_id,
        write=True,
    )
    calculation = _tenant_calculation_or_404(
        session,
        organization_id=organization_id,
        calculation_id=calculation_id,
    )
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
