"""HTTP security regression tests for partner API credential management."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.main import app
from app.models import Organization, OrganizationMembership, User


def _actor(db_session: Session, *, role: str, suffix: str):
    user = User(email=f"partner-{suffix}@example.test", display_name=f"Partner {suffix}")
    organization = Organization(slug=f"partner-{suffix}", legal_name=f"Partner {suffix}")
    db_session.add_all([user, organization])
    db_session.flush()
    db_session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role,
        )
    )
    db_session.flush()
    _, raw_session = issue_session(db_session, user_id=user.id)
    return user, organization, {"Authorization": f"Bearer {raw_session}"}


def test_owner_issues_lists_and_revokes_partner_credential(app_db_session: Session) -> None:
    client = TestClient(app)
    _, organization, headers = _actor(
        app_db_session,
        role="owner",
        suffix="owner",
    )
    path = f"/organizations/{organization.id}/partner-api-credentials"

    created = client.post(path, json={"name": "ERP connector"}, headers=headers)
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    payload = created.json()
    assert payload["raw_token"].startswith("mp_live_")
    assert payload["token_prefix"] == payload["raw_token"][:16]
    assert "token_sha256" not in payload

    listed = client.get(path, headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert "raw_token" not in listed.json()[0]
    assert "token_sha256" not in listed.json()[0]

    credential_id = payload["id"]
    revoked = client.delete(f"{path}/{credential_id}", headers=headers)
    assert revoked.status_code == 204
    assert revoked.content == b""

    repeated = client.delete(f"{path}/{credential_id}", headers=headers)
    assert repeated.status_code == 204

    listed_after = client.get(path, headers=headers)
    assert listed_after.status_code == 200
    assert listed_after.json()[0]["revoked_at"] is not None


def test_viewer_cannot_manage_partner_credentials(app_db_session: Session) -> None:
    client = TestClient(app)
    _, organization, headers = _actor(
        app_db_session,
        role="viewer",
        suffix="viewer",
    )
    path = f"/organizations/{organization.id}/partner-api-credentials"

    assert client.get(path, headers=headers).status_code == 403
    denied = client.post(path, json={"name": "forbidden"}, headers=headers)
    assert denied.status_code == 403


def test_partner_management_requires_bearer_and_hides_foreign_ids(
    app_db_session: Session,
) -> None:
    client = TestClient(app)
    _, first_org, first_headers = _actor(
        app_db_session,
        role="owner",
        suffix="first",
    )
    _, second_org, second_headers = _actor(
        app_db_session,
        role="owner",
        suffix="second",
    )
    first_path = f"/organizations/{first_org.id}/partner-api-credentials"
    second_path = f"/organizations/{second_org.id}/partner-api-credentials"

    missing_auth = client.get(first_path)
    assert missing_auth.status_code == 401

    created = client.post(
        first_path,
        json={"name": "first connector"},
        headers=first_headers,
    )
    assert created.status_code == 201
    credential_id = created.json()["id"]

    foreign = client.delete(
        f"{second_path}/{credential_id}",
        headers=second_headers,
    )
    assert foreign.status_code == 404


def test_partner_management_rejects_extra_fields_and_bounds_pagination(
    app_db_session: Session,
) -> None:
    client = TestClient(app)
    _, organization, headers = _actor(
        app_db_session,
        role="admin",
        suffix="admin",
    )
    path = f"/organizations/{organization.id}/partner-api-credentials"

    extra = client.post(
        path,
        json={"name": "ERP", "role": "owner"},
        headers=headers,
    )
    assert extra.status_code == 422
    assert client.get(f"{path}?limit=101", headers=headers).status_code == 422
    assert client.get(f"{path}?offset=-1", headers=headers).status_code == 422
