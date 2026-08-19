"""HTTP entry point for the Maliyet Platformu API."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

SERVICE_NAME = "maliyet-calculation-api"
SERVICE_VERSION = "0.1.0"


class HealthResponse(BaseModel):
    """Stable health payload used by infrastructure probes."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"]
    service: str
    version: str


app = FastAPI(
    title="Maliyet Platformu API",
    version=SERVICE_VERSION,
    description="Versioned API for costing, finance and integration capabilities.",
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Return a dependency-free process health signal."""

    return HealthResponse(status="ok", service=SERVICE_NAME, version=SERVICE_VERSION)
