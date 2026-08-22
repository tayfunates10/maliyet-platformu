"""Authenticated tenant-private calculation report export API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import AuthenticatedIdentity, AuthorizationError, resolve_actor_context
from app.http_dependencies import get_authenticated_identity, get_database_session
from app.models import Calculation, CalculationVersion
from app.report_export import build_calculation_report_csv

router = APIRouter(tags=["reports"])


def _authorized_calculation_version(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    calculation_id: UUID,
    version_number: int,
) -> tuple[Calculation, CalculationVersion]:
    try:
        resolve_actor_context(
            session,
            identity=identity,
            organization_id=organization_id,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="organization access denied",
        ) from exc

    calculation = session.scalar(
        select(Calculation).where(
            Calculation.id == calculation_id,
            Calculation.organization_id == organization_id,
        )
    )
    if calculation is None:
        raise HTTPException(status_code=404, detail="calculation not found")

    version = session.scalar(
        select(CalculationVersion).where(
            CalculationVersion.organization_id == organization_id,
            CalculationVersion.calculation_id == calculation_id,
            CalculationVersion.version == version_number,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="calculation version not found")
    return calculation, version


@router.get(
    "/organizations/{organization_id}/calculations/{calculation_id}/versions/{version_number}/report.csv",
    response_class=Response,
)
def export_calculation_report_csv(
    organization_id: UUID,
    calculation_id: UUID,
    version_number: int,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> Response:
    """Download one immutable version as deterministic spreadsheet-safe CSV."""

    if version_number < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="version number must be positive",
        )
    calculation, version = _authorized_calculation_version(
        session,
        identity=identity,
        organization_id=organization_id,
        calculation_id=calculation_id,
        version_number=version_number,
    )
    report = build_calculation_report_csv(calculation, version)
    filename = f"calculation-{calculation.id}-v{version.version}.csv"
    return Response(
        content=report.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
