"""Tenant-scoped report export routes for immutable calculation versions."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import (
    AuthenticatedIdentity,
    AuthorizationError,
    resolve_actor_context,
)
from app.http_dependencies import get_authenticated_identity, get_database_session
from app.models import Calculation, CalculationVersion
from app.report_exports import CalculationReportSnapshot, render_report, safe_report_filename

router = APIRouter(tags=["reports"])


@router.get(
    "/organizations/{organization_id}/calculations/{calculation_id}/versions/{version_number}/report",
    response_class=Response,
)
def export_calculation_report(
    organization_id: UUID,
    calculation_id: UUID,
    version_number: int,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
    report_format: Annotated[Literal["web", "xlsx", "docx", "pdf"], Query(alias="format")] = "web",
) -> Response:
    """Render one immutable version without recalculating or crossing tenant boundaries."""

    try:
        resolve_actor_context(session, identity=identity, organization_id=organization_id)
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="organization access denied",
        ) from exc

    row = session.execute(
        select(Calculation, CalculationVersion)
        .join(CalculationVersion, CalculationVersion.calculation_id == Calculation.id)
        .where(
            Calculation.organization_id == organization_id,
            Calculation.id == calculation_id,
            CalculationVersion.organization_id == organization_id,
            CalculationVersion.version == version_number,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="calculation version not found")

    calculation, version = row
    snapshot = CalculationReportSnapshot(
        calculation_name=calculation.name,
        calculation_type=calculation.calculation_type,
        version=version.version,
        engine_key=version.engine_key,
        engine_version=version.engine_version,
        created_at=version.created_at,
        input_sha256=version.input_sha256,
        ruleset_sha256=version.ruleset_sha256,
        output_sha256=version.output_sha256,
        input_snapshot=version.input_snapshot,
        ruleset_snapshot=version.ruleset_snapshot,
        output_snapshot=version.output_snapshot,
    )
    artifact = render_report(snapshot, report_format)
    filename = safe_report_filename(calculation.name, version.version, artifact.extension)
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
