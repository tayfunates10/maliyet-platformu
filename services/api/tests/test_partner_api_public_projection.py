"""Partner API regression tests for customer-safe published projection access."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.main import app
from app.models import (
    Calculation,
    CalculationVersion,
    Organization,
    OrganizationMembership,
    User,
)
from app.partner_api_credentials import (
    issue_partner_api_credential,
    revoke_partner_api_credential,
)

_PRIVATE_SENTINEL = "PRIVATE-COST-DO-NOT-LEAK"


def _tenant(session: Session, *, suffix: str):
    user = User(email=f"partner-public-{suffix}@example.test", display_name=f"Partner {suffix}")
    organization = Organization(
        slug=f"partner-public-{suffix}",
        legal_name=f"Partner Public {suffix}",
    )
    session.add_all([user, organization])
    session.flush()
    session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role="owner",
        )
    )
    session.flush()
    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=user.id,
        name="Private partner source",
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
        engine_version="partner-test-v1",
        input_snapshot={"supplier_cost": _PRIVATE_SENTINEL},
        input_sha256="a" * 64,
        ruleset_snapshot={"private_rule": "do-not-publish"},
        ruleset_sha256="b" * 64,
        output_snapshot={"profit": _PRIVATE_SENTINEL, "margin": "0.40"},
        output_sha256="c" * 64,
    )
    session.add(version)
    session.flush()
    _, user_token = issue_session(session, user_id=user.id)
    partner = issue_partner_api_credential(
        session,
        organization_id=organization.id,
        created_by_user_id=user.id,
        name="Partner reader",
    )
    return user, organization, calculation, user_token, partner


def _publish(client: TestClient, organization, calculation, user_token: str) -> dict[str, object]:
    path = (
        f"/organizations/{organization.id}/calculations/{calculation.id}"
        "/versions/1/public-projections"
    )
    response = client.post(
        path,
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "title": "Partner-visible estimate",
            "currency": "TRY",
            "estimate_min": "1200.50",
            "estimate_max": "1500.75",
        },
    )
    assert response.status_code == 201
    return response.json()


def _partner_path(projection_id: str) -> str:
    return f"/organizations/partner/v1/calculation-projections/{projection_id}"


def test_partner_token_reads_only_customer_safe_projection(app_db_session: Session) -> None:
    _, organization, calculation, user_token, partner = _tenant(
        app_db_session,
        suffix="safe",
    )
    client = TestClient(app)
    published = _publish(client, organization, calculation, user_token)

    response = client.get(
        _partner_path(str(published["projection_id"])),
        headers={"Authorization": f"Bearer {partner.raw_token}"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {
        "title",
        "currency",
        "estimate_min",
        "estimate_max",
        "published_at",
    }
    assert body["title"] == "Partner-visible estimate"
    assert body["estimate_min"] == "1200.5"
    serialized = response.text
    assert _PRIVATE_SENTINEL not in serialized
    assert "supplier_cost" not in serialized
    assert "private_rule" not in serialized
    assert "profit" not in serialized
    assert "margin" not in serialized
    assert str(organization.id) not in serialized
    assert str(calculation.id) not in serialized


def test_partner_projection_access_is_tenant_scoped(app_db_session: Session) -> None:
    _, first_org, first_calculation, first_user_token, _ = _tenant(
        app_db_session,
        suffix="first",
    )
    _, _, _, _, second_partner = _tenant(app_db_session, suffix="second")
    client = TestClient(app)
    published = _publish(client, first_org, first_calculation, first_user_token)

    response = client.get(
        _partner_path(str(published["projection_id"])),
        headers={"Authorization": f"Bearer {second_partner.raw_token}"},
    )

    assert response.status_code == 404


def test_partner_endpoint_rejects_missing_invalid_and_revoked_credentials(
    app_db_session: Session,
) -> None:
    user, organization, calculation, user_token, partner = _tenant(
        app_db_session,
        suffix="auth",
    )
    client = TestClient(app)
    published = _publish(client, organization, calculation, user_token)
    path = _partner_path(str(published["projection_id"]))

    missing = client.get(path)
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"

    invalid = client.get(path, headers={"Authorization": "Bearer not-a-partner-token"})
    assert invalid.status_code == 401

    revoke_partner_api_credential(
        app_db_session,
        organization_id=organization.id,
        credential_id=partner.credential.id,
        revoked_by_user_id=user.id,
    )
    revoked = client.get(path, headers={"Authorization": f"Bearer {partner.raw_token}"})
    assert revoked.status_code == 401


def test_partner_endpoint_hides_revoked_projection(app_db_session: Session) -> None:
    _, organization, calculation, user_token, partner = _tenant(
        app_db_session,
        suffix="projection-revoke",
    )
    client = TestClient(app)
    published = _publish(client, organization, calculation, user_token)
    projection_id = str(published["projection_id"])
    revoke_path = f"/organizations/{organization.id}/public-calculation-projections/{projection_id}"
    revoked = client.delete(
        revoke_path,
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert revoked.status_code == 204

    response = client.get(
        _partner_path(projection_id),
        headers={"Authorization": f"Bearer {partner.raw_token}"},
    )
    assert response.status_code == 404
