"""HTTP entry point for the Maliyet Platformu API."""

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from app.engine_registry import (
    EngineNotFoundError,
    describe_registered_engine,
    list_registered_engines,
)

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
