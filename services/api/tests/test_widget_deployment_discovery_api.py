"""Integration coverage for tenant-scoped widget deployment discovery."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.main import app
from app.models import (
    Calculation,
    CalculationVersion,
    Organization,
    OrganizationMembership,
    PublicCalculationProjection,
    User,
    WidgetAllowedOrigin,
    WidgetDeployment,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _tenant(session: Session, *, suffix: str, role: str) -> tuple[User, Organization, str]:
    user = User(email=f"discovery-{suffix}@example.test", display_name=f"Discovery {suffix}")
    organization = Organization(slug=f"discovery-{suffix}", legal_name=f"Discovery {suffix}")
    session.add_all([user, organization])
    session.flush()
    session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role,
        )
    )
    session.flush()
    _, token = issue_session(session, user_id=user.id)
    return user, organization, token


def _projection(
    session: Session,
    *,
    user: User,
    organization: Organization,
    suffix: str,
) -> PublicCalculationProjection:
    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=user.id,
        name="Discovery source",
        calculation_type="trade",
    )
    session.add(calculation)
    session.flush()
    version = CalculationVersion(
        organization_id=organization.id,
        calculation_id=calculation.id,
        created_by_user_id=user.id,
        version=1,
        engine_key="trade",
        engine_version="discovery-v1",
        input_snapshot={},
        input_sha256=_digest(f"input-{suffix}"),
        ruleset_snapshot={},
        ruleset_sha256=_digest(f"rules-{suffix}"),
        output_snapshot={},
        output_sha256=_digest(f"output-{suffix}"),
    )
    session.add(version)
    session.flush()
    projection = PublicCalculationProjection(
        organization_id=organization.id,
        calculation_version_id=version.id,
        created_by_user_id=user.id,
        token_sha256=_digest(f"token-{suffix}"),
        title="Discovery projection",
        currency="TRY",
        estimate_min="100",
        estimate_max="120",
    )
    session.add(projection)
    session.flush()
    return projection


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_owner_lists_active_disabled_and_revoked_deployments(app_db_session: Session) -> None:
    user, organization, token = _tenant(app_db_session, suffix="owner", role="owner")
    projection = _projection(
        app_db_session,
        user=user,
        organization=organization,
        suffix="owner",
    )
    active = WidgetDeployment(
        organization_id=organization.id,
        public_projection_id=projection.id,
        created_by_user_id=user.id,
        name="Active",
        hourly_request_limit=10,
    )
    disabled = WidgetDeployment(
        organization_id=organization.id,
        public_projection_id=projection.id,
        created_by_user_id=user.id,
        name="Disabled",
        hourly_request_limit=20,
        disabled_at=datetime.now(UTC),
    )
    app_db_session.add_all([active, disabled])
    app_db_session.flush()
    app_db_session.add(
        WidgetAllowedOrigin(
            organization_id=organization.id,
            widget_deployment_id=active.id,
            created_by_user_id=user.id,
            origin="https://shop.example.test",
        )
    )
    app_db_session.flush()

    response = TestClient(app).get(
        f"/organizations/{organization.id}/widget-deployments",
        headers=_headers(token),
    )
    assert response.status_code == 200, response.text
    by_id = {item["id"]: item for item in response.json()}
    assert set(by_id) == {str(active.id), str(disabled.id)}
    assert by_id[str(active.id)]["publishable"] is True
    assert by_id[str(active.id)]["allowed_origins"] == ["https://shop.example.test"]
    assert by_id[str(disabled.id)]["publishable"] is False
    assert by_id[str(disabled.id)]["disabled_at"] is not None
    assert "token_sha256" not in response.text

    projection.revoked_at = datetime.now(UTC)
    app_db_session.flush()
    revoked = TestClient(app).get(
        f"/organizations/{organization.id}/widget-deployments",
        headers=_headers(token),
    )
    assert revoked.status_code == 200
    assert all(item["publishable"] is False for item in revoked.json())
    assert all(item["source_revoked_at"] is not None for item in revoked.json())


def test_discovery_is_owner_admin_only_and_tenant_scoped(app_db_session: Session) -> None:
    _, organization, accountant_token = _tenant(
        app_db_session,
        suffix="accountant",
        role="accountant",
    )
    _, _, other_owner_token = _tenant(app_db_session, suffix="other", role="owner")
    path = f"/organizations/{organization.id}/widget-deployments"
    client = TestClient(app)

    assert client.get(path, headers=_headers(accountant_token)).status_code == 403
    assert client.get(path, headers=_headers(other_owner_token)).status_code == 403
    assert client.get(f"{path}?limit=0", headers=_headers(accountant_token)).status_code == 422
