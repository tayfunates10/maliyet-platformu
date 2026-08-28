"""HTTP route for the read-only tenant dashboard projection.

The route is a thin transport shell: membership is proven first, then the whole
read model is composed by ``app.dashboard_overview`` inside the request
transaction. No financial figure is produced here, and every monetary field
crosses the JSON boundary as the exact string the engine stored.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth_context import AuthenticatedIdentity
from app.dashboard_overview import build_dashboard_overview
from app.http_dependencies import get_authenticated_identity, get_database_session
from app.organization_onboarding import OrganizationAccessDenied, get_organization_access

router = APIRouter(prefix="/{organization_id}/dashboard", tags=["dashboard"])


class DashboardOrganizationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    slug: str
    legal_name: str
    primary_sector: str | None
    city: str | None
    role: str


class CostCategoryGroupResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    entries: dict[str, str]


class DashboardCalculationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    calculation_id: UUID
    name: str
    calculation_type: str
    engine_key: str | None
    engine_title: str | None
    engine_version: str | None
    version_number: int | None
    computed_at: datetime | None
    output_sha256: str | None
    total_cost: str | None
    unit_cost: str | None
    margin_ratio: str | None
    cost_categories: list[CostCategoryGroupResponse]


class DashboardTimelineEntryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    calculation_id: UUID
    calculation_name: str
    engine_key: str | None
    version_number: int
    computed_at: datetime
    total_cost: str | None
    unit_cost: str | None


class RegulatorySourceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    authority: str
    title: str
    official_reference: str | None
    published_on: date | None
    retrieved_at: datetime
    content_sha256: str


class RegulatoryRuleResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    category: str
    description: str
    state: Literal["effective", "not_effective", "ambiguous"]
    effective_from: date | None
    effective_to: date | None
    revision: int | None


class RegulatoryBaselineResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ready", "degraded", "unavailable"]
    dataset: str | None
    dataset_version: int | None
    reviewed_on: date | None
    evaluated_at: date
    source_count: int
    rule_count: int
    effective_rule_count: int
    issues: list[str]
    sources: list[RegulatorySourceResponse]
    rules: list[RegulatoryRuleResponse]


class DecisionAnalysisSummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_count: int
    latest_artifact_id: UUID | None
    latest_engine_version: str | None
    latest_created_at: datetime | None
    latest_output_sha256: str | None


class WidgetSummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    deployment_count: int
    active_deployment_count: int
    branding_profile_count: int
    published_presentation_count: int


class DashboardResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    organization: DashboardOrganizationResponse
    generated_at: datetime
    calculation_count: int
    calculations: list[DashboardCalculationResponse]
    timeline: list[DashboardTimelineEntryResponse]
    regulatory_baseline: RegulatoryBaselineResponse
    decision_analysis: DecisionAnalysisSummaryResponse
    widget: WidgetSummaryResponse


@router.get(
    "",
    response_model=DashboardResponse,
    tags=["dashboard"],
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Organization not found for this member"},
    },
)
def read_dashboard(
    organization_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> DashboardResponse:
    """Return one tenant-scoped dashboard projection for the authenticated member."""

    try:
        access = get_organization_access(
            session,
            authenticated_user_id=identity.user_id,
            organization_id=organization_id,
        )
    except OrganizationAccessDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="organization not found",
        ) from exc

    generated_at = datetime.now(tz=UTC)
    overview = build_dashboard_overview(
        session,
        organization_id=organization_id,
        generated_at=generated_at,
        at_date=generated_at.date(),
    )
    profile = access.business_profile
    return DashboardResponse(
        organization=DashboardOrganizationResponse(
            id=access.organization.id,
            slug=access.organization.slug,
            legal_name=access.organization.legal_name,
            primary_sector=profile.primary_sector if profile is not None else None,
            city=profile.city if profile is not None else None,
            role=access.membership.role,
        ),
        generated_at=overview.generated_at,
        calculation_count=overview.calculation_count,
        calculations=[
            DashboardCalculationResponse(
                calculation_id=item.calculation_id,
                name=item.name,
                calculation_type=item.calculation_type,
                engine_key=item.engine_key,
                engine_title=item.engine_title,
                engine_version=item.engine_version,
                version_number=item.version_number,
                computed_at=item.computed_at,
                output_sha256=item.output_sha256,
                total_cost=item.total_cost,
                unit_cost=item.unit_cost,
                margin_ratio=item.margin_ratio,
                cost_categories=[
                    CostCategoryGroupResponse(key=group.key, entries=dict(group.entries))
                    for group in item.cost_categories
                ],
            )
            for item in overview.calculations
        ],
        timeline=[
            DashboardTimelineEntryResponse(
                calculation_id=entry.calculation_id,
                calculation_name=entry.calculation_name,
                engine_key=entry.engine_key,
                version_number=entry.version_number,
                computed_at=entry.computed_at,
                total_cost=entry.total_cost,
                unit_cost=entry.unit_cost,
            )
            for entry in overview.timeline
        ],
        regulatory_baseline=RegulatoryBaselineResponse(
            status=overview.regulatory_baseline.status,
            dataset=overview.regulatory_baseline.dataset,
            dataset_version=overview.regulatory_baseline.dataset_version,
            reviewed_on=overview.regulatory_baseline.reviewed_on,
            evaluated_at=overview.regulatory_baseline.evaluated_at,
            source_count=overview.regulatory_baseline.source_count,
            rule_count=overview.regulatory_baseline.rule_count,
            effective_rule_count=overview.regulatory_baseline.effective_rule_count,
            issues=list(overview.regulatory_baseline.issues),
            sources=[
                RegulatorySourceResponse(
                    authority=source.authority,
                    title=source.title,
                    official_reference=source.official_reference,
                    published_on=source.published_on,
                    retrieved_at=source.retrieved_at,
                    content_sha256=source.content_sha256,
                )
                for source in overview.regulatory_baseline.sources
            ],
            rules=[
                RegulatoryRuleResponse(
                    code=rule.code,
                    category=rule.category,
                    description=rule.description,
                    state=rule.state,
                    effective_from=rule.effective_from,
                    effective_to=rule.effective_to,
                    revision=rule.revision,
                )
                for rule in overview.regulatory_baseline.rules
            ],
        ),
        decision_analysis=DecisionAnalysisSummaryResponse(
            artifact_count=overview.decision_analysis.artifact_count,
            latest_artifact_id=overview.decision_analysis.latest_artifact_id,
            latest_engine_version=overview.decision_analysis.latest_engine_version,
            latest_created_at=overview.decision_analysis.latest_created_at,
            latest_output_sha256=overview.decision_analysis.latest_output_sha256,
        ),
        widget=WidgetSummaryResponse(
            deployment_count=overview.widget.deployment_count,
            active_deployment_count=overview.widget.active_deployment_count,
            branding_profile_count=overview.widget.branding_profile_count,
            published_presentation_count=overview.widget.published_presentation_count,
        ),
    )
