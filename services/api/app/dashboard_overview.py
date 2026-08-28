"""Read-only tenant dashboard aggregation over already-computed artifacts.

This module is deliberately not a calculation engine. It never adds, divides or
otherwise derives a monetary figure: every amount it returns is copied verbatim
out of an immutable ``CalculationVersion.output_snapshot`` that a registered
engine produced under its own Decimal context. Values therefore stay strings
across the whole read path and never pass through binary floating point.

Two consequences are intentional and must not be "fixed" by summing here:

* Engines publish different authoritative headline fields, and some publish no
  grand total at all. A missing headline metric is reported as ``None`` so the
  UI can render an explicit empty state instead of an invented number.
* Totals are never combined across engines. A food batch cost and a haulage
  route cost are different financial objects; adding them would be a new
  business rule invented in a read model.

Regulatory readiness is delegated to the canonical baseline verifier and fails
closed: any drift, missing rule or unresolvable effective date downgrades the
reported status, and no code path can report a clean baseline it did not prove.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.baseline_loader import (
    BaselineIntegrityError,
    BaselineManifest,
    read_manifest,
    verify_tr_2026_baseline_state,
)
from app.decision_analysis_models import DecisionAnalysisArtifact
from app.engine_registry import describe_registered_engine
from app.models import Calculation, CalculationVersion, WidgetDeployment
from app.rules_engine import RuleConfigurationError, RuleNotFound, resolve_rule
from app.widget_branding_models import WidgetBrandingProfile, WidgetPublishedPresentation

MAX_DASHBOARD_CALCULATIONS = 50
MAX_TIMELINE_VERSIONS = 60

BaselineStatus = Literal["ready", "degraded", "unavailable"]


@dataclass(frozen=True)
class EngineHeadlineFields:
    """Which already-computed snapshot keys an engine publishes as headline figures.

    This is metadata about existing engine output, not a formula. ``None`` means
    the engine genuinely does not publish that figure, and the dashboard must
    show an empty state rather than deriving one.
    """

    total_cost_key: str | None = None
    unit_cost_key: str | None = None
    margin_ratio_key: str | None = None


# Keys below are the engines' own authoritative snapshot fields. They were read
# from each engine's snapshot builder; none of them is computed here.
ENGINE_HEADLINE_FIELDS: dict[str, EngineHeadlineFields] = {
    "food_manufacturing": EngineHeadlineFields(unit_cost_key="package_unit_cost"),
    "textile_manufacturing": EngineHeadlineFields(unit_cost_key="finished_piece_unit_cost"),
    "basic_metals": EngineHeadlineFields(unit_cost_key="finished_output_unit_cost"),
    # Commerce engines publish channel-fee and acquisition subtotals but no
    # grand total, so no field is claimed as one.
    "ecommerce": EngineHeadlineFields(margin_ratio_key="contribution_margin_ratio"),
    "trade": EngineHeadlineFields(margin_ratio_key="contribution_margin_ratio"),
    "transportation": EngineHeadlineFields(
        total_cost_key="total_trip_cost",
        unit_cost_key="cost_per_total_km",
    ),
    "accommodation": EngineHeadlineFields(
        total_cost_key="total_operating_cost",
        unit_cost_key="cost_per_occupied_room_night",
        margin_ratio_key="contribution_margin_ratio",
    ),
    "tourism": EngineHeadlineFields(
        total_cost_key="total_package_cost",
        unit_cost_key="cost_per_participant",
        margin_ratio_key="contribution_margin_ratio",
    ),
    "personnel_cost": EngineHeadlineFields(total_cost_key="total_employer_cost"),
    "asset_depreciation": EngineHeadlineFields(total_cost_key="acquisition_cost"),
    "target_profit_pricing": EngineHeadlineFields(unit_cost_key="variable_cost_per_unit"),
    "tax_reconciliation": EngineHeadlineFields(),
}


@dataclass(frozen=True)
class CostCategoryGroup:
    """One engine-published cost breakdown, kept exactly as the engine wrote it."""

    key: str
    entries: dict[str, str]


@dataclass(frozen=True)
class CalculationOverview:
    """One tenant calculation with the headline figures of its newest version."""

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
    cost_categories: tuple[CostCategoryGroup, ...]


@dataclass(frozen=True)
class VersionTimelineEntry:
    """One immutable version execution, ordered oldest first."""

    calculation_id: UUID
    calculation_name: str
    engine_key: str | None
    version_number: int
    computed_at: datetime
    total_cost: str | None
    unit_cost: str | None


@dataclass(frozen=True)
class RegulatorySourceSummary:
    """Provenance of one curated regulatory source."""

    authority: str
    title: str
    official_reference: str | None
    published_on: date | None
    retrieved_at: datetime
    content_sha256: str


@dataclass(frozen=True)
class RegulatoryRuleSummary:
    """Effective-date state of one curated rule at the requested date."""

    code: str
    category: str
    description: str
    state: Literal["effective", "not_effective", "ambiguous"]
    effective_from: date | None
    effective_to: date | None
    revision: int | None


@dataclass(frozen=True)
class RegulatoryBaselineOverview:
    """Baseline integrity and effective-date coverage. Never a compliance score."""

    status: BaselineStatus
    dataset: str | None
    dataset_version: int | None
    reviewed_on: date | None
    evaluated_at: date
    source_count: int
    rule_count: int
    effective_rule_count: int
    issues: tuple[str, ...]
    sources: tuple[RegulatorySourceSummary, ...]
    rules: tuple[RegulatoryRuleSummary, ...]


@dataclass(frozen=True)
class DecisionAnalysisOverview:
    """Counts and provenance of stored decision artifacts, without replaying them."""

    artifact_count: int
    latest_artifact_id: UUID | None
    latest_engine_version: str | None
    latest_created_at: datetime | None
    latest_output_sha256: str | None


@dataclass(frozen=True)
class WidgetOverview:
    """Widget distribution state for this tenant."""

    deployment_count: int
    active_deployment_count: int
    branding_profile_count: int
    published_presentation_count: int


@dataclass(frozen=True)
class DashboardOverview:
    """Everything one tenant dashboard render needs, from one transaction."""

    generated_at: datetime
    calculation_count: int
    calculations: tuple[CalculationOverview, ...]
    timeline: tuple[VersionTimelineEntry, ...]
    regulatory_baseline: RegulatoryBaselineOverview
    decision_analysis: DecisionAnalysisOverview
    widget: WidgetOverview


def _decimal_text(snapshot: dict[str, object], key: str | None) -> str | None:
    """Read one engine-published scalar verbatim; anything else is treated as absent."""

    if key is None:
        return None
    value = snapshot.get(key)
    return value if isinstance(value, str) and value != "" else None


def _is_cost_breakdown_key(key: str) -> bool:
    """Whether one snapshot mapping is a cost breakdown rather than another map.

    Engines also publish revenue maps (for example ``channel_revenue_totals``)
    with the same shape. Selecting purely on shape would put revenue into a cost
    table, so the name must read as a cost breakdown and must not be revenue.
    The rule stays structural: no engine key is hardcoded.
    """

    if "revenue" in key:
        return False
    return "cost" in key or "category" in key or "stage" in key


def _cost_category_groups(snapshot: dict[str, object]) -> tuple[CostCategoryGroup, ...]:
    """Collect the engine's own cost breakdown maps without interpreting them.

    Selection is structural: a mapping whose values are all non-empty strings is
    an engine-published Decimal breakdown. No engine-specific key is hardcoded,
    so a new engine's breakdown is picked up without touching this module.
    """

    groups: list[CostCategoryGroup] = []
    for key in sorted(snapshot):
        if not _is_cost_breakdown_key(key):
            continue
        value = snapshot[key]
        if not isinstance(value, dict) or not value:
            continue
        entries = {
            str(name): amount
            for name, amount in sorted(value.items())
            if isinstance(amount, str) and amount != ""
        }
        if len(entries) == len(value):
            groups.append(CostCategoryGroup(key=key, entries=entries))
    return tuple(groups)


def _engine_labels(engine_key: str | None) -> tuple[str | None, str | None]:
    if engine_key is None:
        return None, None
    try:
        descriptor = describe_registered_engine(engine_key)
    except LookupError:
        return None, None
    return descriptor.title, descriptor.engine_version


def _latest_versions(
    session: Session,
    *,
    organization_id: UUID,
    calculation_ids: list[UUID],
) -> dict[UUID, CalculationVersion]:
    """Newest version per calculation, scoped to the tenant at the query level."""

    if not calculation_ids:
        return {}
    newest = (
        select(
            CalculationVersion.calculation_id.label("calculation_id"),
            func.max(CalculationVersion.version).label("version"),
        )
        .where(
            CalculationVersion.organization_id == organization_id,
            CalculationVersion.calculation_id.in_(calculation_ids),
        )
        .group_by(CalculationVersion.calculation_id)
        .subquery()
    )
    rows = session.scalars(
        select(CalculationVersion).join(
            newest,
            (CalculationVersion.calculation_id == newest.c.calculation_id)
            & (CalculationVersion.version == newest.c.version),
        )
    ).all()
    return {row.calculation_id: row for row in rows}


def _calculation_overviews(
    session: Session,
    *,
    organization_id: UUID,
) -> tuple[int, tuple[CalculationOverview, ...]]:
    total = session.scalar(
        select(func.count())
        .select_from(Calculation)
        .where(Calculation.organization_id == organization_id)
    )
    calculations = session.scalars(
        select(Calculation)
        .where(Calculation.organization_id == organization_id)
        .order_by(Calculation.created_at.desc(), Calculation.id.desc())
        .limit(MAX_DASHBOARD_CALCULATIONS)
    ).all()
    versions = _latest_versions(
        session,
        organization_id=organization_id,
        calculation_ids=[item.id for item in calculations],
    )

    overviews: list[CalculationOverview] = []
    for calculation in calculations:
        version = versions.get(calculation.id)
        if version is None:
            overviews.append(
                CalculationOverview(
                    calculation_id=calculation.id,
                    name=calculation.name,
                    calculation_type=calculation.calculation_type,
                    engine_key=None,
                    engine_title=None,
                    engine_version=None,
                    version_number=None,
                    computed_at=None,
                    output_sha256=None,
                    total_cost=None,
                    unit_cost=None,
                    margin_ratio=None,
                    cost_categories=(),
                )
            )
            continue

        snapshot = version.output_snapshot
        headline = ENGINE_HEADLINE_FIELDS.get(version.engine_key or "", EngineHeadlineFields())
        title, engine_version = _engine_labels(version.engine_key)
        overviews.append(
            CalculationOverview(
                calculation_id=calculation.id,
                name=calculation.name,
                calculation_type=calculation.calculation_type,
                engine_key=version.engine_key,
                engine_title=title,
                engine_version=engine_version or version.engine_version,
                version_number=version.version,
                computed_at=version.created_at,
                output_sha256=version.output_sha256,
                total_cost=_decimal_text(snapshot, headline.total_cost_key),
                unit_cost=_decimal_text(snapshot, headline.unit_cost_key),
                margin_ratio=_decimal_text(snapshot, headline.margin_ratio_key),
                cost_categories=_cost_category_groups(snapshot),
            )
        )
    return int(total or 0), tuple(overviews)


def _timeline(session: Session, *, organization_id: UUID) -> tuple[VersionTimelineEntry, ...]:
    rows = session.execute(
        select(CalculationVersion, Calculation.name)
        .join(Calculation, Calculation.id == CalculationVersion.calculation_id)
        .where(CalculationVersion.organization_id == organization_id)
        .order_by(CalculationVersion.created_at.desc(), CalculationVersion.version.desc())
        .limit(MAX_TIMELINE_VERSIONS)
    ).all()

    entries: list[VersionTimelineEntry] = []
    for version, calculation_name in rows:
        headline = ENGINE_HEADLINE_FIELDS.get(version.engine_key or "", EngineHeadlineFields())
        entries.append(
            VersionTimelineEntry(
                calculation_id=version.calculation_id,
                calculation_name=calculation_name,
                engine_key=version.engine_key,
                version_number=version.version,
                computed_at=version.created_at,
                total_cost=_decimal_text(version.output_snapshot, headline.total_cost_key),
                unit_cost=_decimal_text(version.output_snapshot, headline.unit_cost_key),
            )
        )
    entries.reverse()
    return tuple(entries)


def _rule_states(
    session: Session,
    manifest: BaselineManifest,
    *,
    at_date: date,
) -> tuple[tuple[RegulatoryRuleSummary, ...], tuple[str, ...]]:
    """Resolve every curated rule through the canonical resolver, fail-closed."""

    summaries: list[RegulatoryRuleSummary] = []
    issues: list[str] = []
    for rule in manifest.rules:
        try:
            resolved = resolve_rule(session, jurisdiction="TR", code=rule.code, at_date=at_date)
        except RuleNotFound:
            summaries.append(
                RegulatoryRuleSummary(
                    code=rule.code,
                    category=rule.category,
                    description=rule.description,
                    state="not_effective",
                    effective_from=None,
                    effective_to=None,
                    revision=None,
                )
            )
            issues.append(f"{rule.code}: no effective version at {at_date.isoformat()}")
            continue
        except RuleConfigurationError:
            summaries.append(
                RegulatoryRuleSummary(
                    code=rule.code,
                    category=rule.category,
                    description=rule.description,
                    state="ambiguous",
                    effective_from=None,
                    effective_to=None,
                    revision=None,
                )
            )
            issues.append(f"{rule.code}: ambiguous effective versions at {at_date.isoformat()}")
            continue

        version = resolved.version
        summaries.append(
            RegulatoryRuleSummary(
                code=rule.code,
                category=rule.category,
                description=rule.description,
                state="effective",
                effective_from=version.effective_from,
                effective_to=version.effective_to,
                revision=version.revision,
            )
        )
    return tuple(summaries), tuple(issues)


def _unavailable_baseline(at_date: date, *, reason: str) -> RegulatoryBaselineOverview:
    return RegulatoryBaselineOverview(
        status="unavailable",
        dataset=None,
        dataset_version=None,
        reviewed_on=None,
        evaluated_at=at_date,
        source_count=0,
        rule_count=0,
        effective_rule_count=0,
        issues=(reason,),
        sources=(),
        rules=(),
    )


def regulatory_baseline_overview(
    session: Session,
    *,
    at_date: date,
) -> RegulatoryBaselineOverview:
    """Report baseline integrity and coverage without ever asserting unproven health."""

    try:
        manifest = read_manifest()
    except (OSError, ValueError) as exc:
        return _unavailable_baseline(at_date, reason=f"baseline manifest unreadable: {exc}")

    integrity_issues: list[str] = []
    try:
        verify_tr_2026_baseline_state(session)
    except BaselineIntegrityError as exc:
        integrity_issues.append(f"baseline integrity verification failed: {exc}")
    except (OSError, ValueError) as exc:
        return _unavailable_baseline(at_date, reason=f"baseline verification unavailable: {exc}")

    rules, rule_issues = _rule_states(session, manifest, at_date=at_date)
    effective_count = sum(1 for rule in rules if rule.state == "effective")
    issues = tuple(integrity_issues) + rule_issues
    status: BaselineStatus = "ready" if not issues else "degraded"

    sources = tuple(
        RegulatorySourceSummary(
            authority=source.authority,
            title=source.title,
            official_reference=source.official_reference,
            published_on=source.published_on,
            retrieved_at=source.retrieved_at,
            content_sha256=source.content_sha256,
        )
        for source in manifest.sources
    )
    return RegulatoryBaselineOverview(
        status=status,
        dataset=manifest.dataset,
        dataset_version=manifest.dataset_version,
        reviewed_on=manifest.reviewed_on,
        evaluated_at=at_date,
        source_count=len(manifest.sources),
        rule_count=len(rules),
        effective_rule_count=effective_count,
        issues=issues,
        sources=sources,
        rules=rules,
    )


def _decision_overview(session: Session, *, organization_id: UUID) -> DecisionAnalysisOverview:
    count = session.scalar(
        select(func.count())
        .select_from(DecisionAnalysisArtifact)
        .where(DecisionAnalysisArtifact.organization_id == organization_id)
    )
    latest = session.scalars(
        select(DecisionAnalysisArtifact)
        .where(DecisionAnalysisArtifact.organization_id == organization_id)
        .order_by(DecisionAnalysisArtifact.created_at.desc())
        .limit(1)
    ).one_or_none()
    if latest is None:
        return DecisionAnalysisOverview(
            artifact_count=int(count or 0),
            latest_artifact_id=None,
            latest_engine_version=None,
            latest_created_at=None,
            latest_output_sha256=None,
        )
    return DecisionAnalysisOverview(
        artifact_count=int(count or 0),
        latest_artifact_id=latest.id,
        latest_engine_version=latest.engine_version,
        latest_created_at=latest.created_at,
        latest_output_sha256=latest.output_sha256,
    )


def _widget_overview(session: Session, *, organization_id: UUID) -> WidgetOverview:
    deployments = session.scalars(
        select(WidgetDeployment).where(WidgetDeployment.organization_id == organization_id)
    ).all()
    branding_count = session.scalar(
        select(func.count())
        .select_from(WidgetBrandingProfile)
        .where(WidgetBrandingProfile.organization_id == organization_id)
    )
    published_count = session.scalar(
        select(func.count())
        .select_from(WidgetPublishedPresentation)
        .where(WidgetPublishedPresentation.organization_id == organization_id)
    )
    return WidgetOverview(
        deployment_count=len(deployments),
        active_deployment_count=sum(1 for item in deployments if item.disabled_at is None),
        branding_profile_count=int(branding_count or 0),
        published_presentation_count=int(published_count or 0),
    )


def build_dashboard_overview(
    session: Session,
    *,
    organization_id: UUID,
    generated_at: datetime,
    at_date: date,
) -> DashboardOverview:
    """Compose one tenant dashboard read model inside the caller's transaction."""

    calculation_count, calculations = _calculation_overviews(
        session, organization_id=organization_id
    )
    return DashboardOverview(
        generated_at=generated_at,
        calculation_count=calculation_count,
        calculations=calculations,
        timeline=_timeline(session, organization_id=organization_id),
        regulatory_baseline=regulatory_baseline_overview(session, at_date=at_date),
        decision_analysis=_decision_overview(session, organization_id=organization_id),
        widget=_widget_overview(session, organization_id=organization_id),
    )
