"""HTTP integration tests for the read-only tenant dashboard projection."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.baseline_loader import load_tr_2026_baseline
from app.dashboard_overview import (
    ENGINE_HEADLINE_FIELDS,
    build_dashboard_overview,
    regulatory_baseline_overview,
)
from app.engine_registry import list_registered_engines
from app.main import app
from app.models import Calculation, CalculationVersion, Organization, OrganizationMembership, User
from app.rules_models import RuleDefinition, RuleSource, RuleVersion


def _tenant(
    db_session: Session,
    *,
    suffix: str,
    role: str = "owner",
) -> tuple[User, Organization, str]:
    user = User(email=f"dashboard-{suffix}@example.test", display_name=f"Dashboard {suffix}")
    organization = Organization(slug=f"dashboard-{suffix}", legal_name=f"Dashboard {suffix} Org")
    db_session.add_all([user, organization])
    db_session.flush()
    db_session.add(
        OrganizationMembership(organization_id=organization.id, user_id=user.id, role=role)
    )
    db_session.flush()
    _, token = issue_session(db_session, user_id=user.id)
    return user, organization, token


def _recorded_calculation(
    db_session: Session,
    *,
    user: User,
    organization: Organization,
    name: str,
    engine_key: str = "food_manufacturing",
    output_snapshot: dict[str, object] | None = None,
) -> Calculation:
    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=user.id,
        name=name,
        calculation_type=engine_key,
    )
    db_session.add(calculation)
    db_session.flush()
    db_session.add(
        CalculationVersion(
            organization_id=organization.id,
            calculation_id=calculation.id,
            created_by_user_id=user.id,
            version=1,
            engine_key=engine_key,
            engine_version=f"{engine_key}-v1",
            input_snapshot={},
            ruleset_snapshot={},
            output_snapshot=output_snapshot
            or {
                "package_unit_cost": "59.17729627118644067796610169",
                "food_process_category_costs": {"labor": "148000.00", "energy": "62500.00"},
            },
        )
    )
    db_session.flush()
    return calculation


def test_dashboard_requires_authentication(app_db_session: Session) -> None:
    _, organization, _ = _tenant(app_db_session, suffix="anon")
    with TestClient(app) as client:
        response = client.get(f"/organizations/{organization.id}/dashboard")
    assert response.status_code == 401


def test_dashboard_reports_engine_published_values_verbatim(app_db_session: Session) -> None:
    user, organization, token = _tenant(app_db_session, suffix="values")
    _recorded_calculation(
        app_db_session,
        user=user,
        organization=organization,
        name="Tahin Helva Parti",
    )

    with TestClient(app) as client:
        response = client.get(
            f"/organizations/{organization.id}/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["calculation_count"] == 1
    entry = body["calculations"][0]
    assert entry["name"] == "Tahin Helva Parti"
    assert entry["engine_key"] == "food_manufacturing"
    # Full Decimal precision survives the read path; no rounding, no float.
    assert entry["unit_cost"] == "59.17729627118644067796610169"
    # The food engine publishes no grand total, so the dashboard must not invent one.
    assert entry["total_cost"] is None
    assert entry["margin_ratio"] is None
    assert entry["cost_categories"] == [
        {
            "key": "food_process_category_costs",
            "entries": {"energy": "62500.00", "labor": "148000.00"},
        }
    ]


def test_dashboard_is_tenant_isolated(app_db_session: Session) -> None:
    owner_a, organization_a, token_a = _tenant(app_db_session, suffix="iso-a")
    owner_b, organization_b, token_b = _tenant(app_db_session, suffix="iso-b")
    _recorded_calculation(
        app_db_session, user=owner_a, organization=organization_a, name="Tenant A batch"
    )
    _recorded_calculation(
        app_db_session, user=owner_b, organization=organization_b, name="Tenant B batch"
    )

    with TestClient(app) as client:
        own = client.get(
            f"/organizations/{organization_a.id}/dashboard",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        crossed = client.get(
            f"/organizations/{organization_b.id}/dashboard",
            headers={"Authorization": f"Bearer {token_a}"},
        )

    assert own.status_code == 200
    names = [item["name"] for item in own.json()["calculations"]]
    assert names == ["Tenant A batch"]
    assert "Tenant B batch" not in str(own.json())
    # A member of another organization must not learn that this tenant exists.
    assert crossed.status_code == 404
    assert token_b


def test_dashboard_empty_tenant_reports_no_data_instead_of_zeros(
    app_db_session: Session,
) -> None:
    _, organization, token = _tenant(app_db_session, suffix="empty")

    with TestClient(app) as client:
        response = client.get(
            f"/organizations/{organization.id}/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["calculation_count"] == 0
    assert body["calculations"] == []
    assert body["timeline"] == []
    assert body["decision_analysis"]["artifact_count"] == 0
    assert body["decision_analysis"]["latest_artifact_id"] is None
    assert body["widget"]["deployment_count"] == 0


def test_dashboard_timeline_is_chronological(app_db_session: Session) -> None:
    user, organization, token = _tenant(app_db_session, suffix="timeline")
    calculation = _recorded_calculation(
        app_db_session, user=user, organization=organization, name="Seri"
    )
    app_db_session.add(
        CalculationVersion(
            organization_id=organization.id,
            calculation_id=calculation.id,
            created_by_user_id=user.id,
            version=2,
            engine_key="food_manufacturing",
            engine_version="food-manufacturing-v1",
            input_snapshot={},
            ruleset_snapshot={},
            output_snapshot={"package_unit_cost": "61.50"},
        )
    )
    app_db_session.flush()

    with TestClient(app) as client:
        response = client.get(
            f"/organizations/{organization.id}/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )

    body = response.json()
    versions = [entry["version_number"] for entry in body["timeline"]]
    assert versions == sorted(versions), "timeline must read oldest to newest"
    # The dashboard headline follows the newest version only.
    assert body["calculations"][0]["version_number"] == 2
    assert body["calculations"][0]["unit_cost"] == "61.50"


def test_regulatory_baseline_fails_closed_when_rules_are_missing(db_session: Session) -> None:
    # Remove the persisted rule base inside this transaction so the state is
    # deterministic regardless of what other suites left in the database.
    db_session.execute(delete(RuleVersion))
    db_session.execute(delete(RuleDefinition))
    db_session.execute(delete(RuleSource))
    db_session.flush()

    overview = regulatory_baseline_overview(db_session, at_date=date(2026, 6, 1))

    # Without a verified rule base a clean bill of health is impossible.
    assert overview.status != "ready"
    assert overview.issues
    assert overview.effective_rule_count == 0


def test_regulatory_baseline_reports_ready_only_after_verified_load(
    db_session: Session,
) -> None:
    load_tr_2026_baseline(db_session)
    db_session.flush()

    overview = regulatory_baseline_overview(db_session, at_date=date(2026, 6, 1))

    assert overview.status == "ready"
    assert overview.issues == ()
    assert overview.rule_count > 0
    assert overview.effective_rule_count == overview.rule_count
    assert overview.source_count > 0
    for source in overview.sources:
        assert len(source.content_sha256) == 64
    for rule in overview.rules:
        assert rule.state == "effective"


def test_regulatory_baseline_degrades_outside_effective_window(db_session: Session) -> None:
    load_tr_2026_baseline(db_session)
    db_session.flush()

    overview = regulatory_baseline_overview(db_session, at_date=date(1999, 1, 1))

    assert overview.status == "degraded"
    assert overview.effective_rule_count == 0
    assert overview.issues
    assert all(rule.state == "not_effective" for rule in overview.rules)


def test_dashboard_overview_never_sums_across_engines(app_db_session: Session) -> None:
    user, organization, _ = _tenant(app_db_session, suffix="no-sum")
    _recorded_calculation(
        app_db_session,
        user=user,
        organization=organization,
        name="Konaklama",
        engine_key="accommodation",
        output_snapshot={"total_operating_cost": "1000.00"},
    )
    _recorded_calculation(
        app_db_session,
        user=user,
        organization=organization,
        name="Ulastirma",
        engine_key="transportation",
        output_snapshot={"total_trip_cost": "250.00"},
    )

    overview = build_dashboard_overview(
        app_db_session,
        organization_id=organization.id,
        generated_at=datetime.now(tz=UTC),
        at_date=date(2026, 6, 1),
    )

    totals = sorted(item.total_cost for item in overview.calculations if item.total_cost)
    assert totals == ["1000.00", "250.00"]
    # There is deliberately no cross-engine aggregate field to report.
    assert not hasattr(overview, "total_cost")


def test_headline_field_declarations_cover_every_registered_engine() -> None:
    registered = {descriptor.key for descriptor in list_registered_engines()}
    declared = set(ENGINE_HEADLINE_FIELDS)
    assert registered <= declared, f"undeclared engines: {sorted(registered - declared)}"
    assert declared <= registered, f"stale declarations: {sorted(declared - registered)}"


def test_revenue_maps_never_enter_the_cost_breakdown(app_db_session: Session) -> None:
    user, organization, token = _tenant(app_db_session, suffix="revenue")
    _recorded_calculation(
        app_db_session,
        user=user,
        organization=organization,
        name="Konaklama sezonu",
        engine_key="accommodation",
        output_snapshot={
            "total_operating_cost": "7170600.00",
            "cost_category_totals": {"energy": "1485000.00", "personnel": "2760000.00"},
            # Same shape as a cost map, but it is revenue and must be excluded.
            "channel_revenue_totals": {"direct": "7045000.00", "ota": "11206000.00"},
        },
    )

    with TestClient(app) as client:
        response = client.get(
            f"/organizations/{organization.id}/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )

    entry = response.json()["calculations"][0]
    group_keys = [group["key"] for group in entry["cost_categories"]]
    assert group_keys == ["cost_category_totals"]
    assert "7045000.00" not in str(entry), "revenue must not reach a cost breakdown"


def test_headline_total_uses_the_engines_own_grand_total(app_db_session: Session) -> None:
    user, organization, token = _tenant(app_db_session, suffix="grand-total")
    _recorded_calculation(
        app_db_session,
        user=user,
        organization=organization,
        name="Sefer",
        engine_key="transportation",
        output_snapshot={
            "total_trip_cost": "25585.3410",
            "route_cost": "2460.00",
            "cost_per_total_km": "31.58684074074074074074074074",
        },
    )

    with TestClient(app) as client:
        response = client.get(
            f"/organizations/{organization.id}/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )

    entry = response.json()["calculations"][0]
    # route_cost is only the tolls; the trip total is the engine's headline.
    assert entry["total_cost"] == "25585.3410"
    assert entry["unit_cost"] == "31.58684074074074074074074074"


def test_engines_without_a_grand_total_report_none(app_db_session: Session) -> None:
    user, organization, token = _tenant(app_db_session, suffix="no-total")
    _recorded_calculation(
        app_db_session,
        user=user,
        organization=organization,
        name="E-ticaret",
        engine_key="ecommerce",
        output_snapshot={
            "total_channel_cost": "18400.00",
            "contribution_margin_ratio": "0.2153",
        },
    )

    with TestClient(app) as client:
        response = client.get(
            f"/organizations/{organization.id}/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )

    entry = response.json()["calculations"][0]
    # Channel fees are not a grand total, so none is claimed.
    assert entry["total_cost"] is None
    assert entry["margin_ratio"] == "0.2153"
