"""HTTP integration tests for local authentication lifecycle."""

import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import AuthSession
from app.main import CurrentUserResponse, SessionTokenResponse, app
from app.models import User
from app.password_auth import UserCredential

TEST_SECRET = "synthetic test credential 2026"
INVALID_SECRET = "synthetic invalid credential"


def _register(client: TestClient, *, email: str) -> SessionTokenResponse:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "display_name": "  Test User  ",
            "password": TEST_SECRET,
        },
    )
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    return SessionTokenResponse.model_validate(response.json())


def test_registration_normalizes_identity_and_never_stores_raw_secrets(
    app_db_session: Session,
) -> None:
    client = TestClient(app)
    token = _register(client, email="  USER@Example.Test ")

    user = app_db_session.scalar(select(User).where(User.id == token.user_id))
    assert user is not None
    assert user.email == "user@example.test"
    assert user.display_name == "Test User"

    credential = app_db_session.get(UserCredential, user.id)
    assert credential is not None
    assert credential.password_hash.startswith("scrypt$v=1$")
    assert TEST_SECRET not in credential.password_hash

    stored_session = app_db_session.scalar(
        select(AuthSession).where(AuthSession.user_id == user.id)
    )
    assert stored_session is not None
    assert token.access_token != stored_session.token_sha256
    assert (
        stored_session.token_sha256
        == hashlib.sha256(token.access_token.encode("utf-8")).hexdigest()
    )


def test_duplicate_registration_is_rejected(app_db_session: Session) -> None:
    client = TestClient(app)
    _register(client, email="duplicate@example.test")

    response = client.post(
        "/auth/register",
        json={
            "email": "DUPLICATE@example.test",
            "display_name": "Other",
            "password": TEST_SECRET,
        },
    )

    assert response.status_code == 409


def test_failed_login_updates_counter_then_success_resets_it(app_db_session: Session) -> None:
    client = TestClient(app)
    registered = _register(client, email="login@example.test")
    credential = app_db_session.get(UserCredential, registered.user_id)
    assert credential is not None

    failed = client.post(
        "/auth/login",
        json={"email": "login@example.test", "password": INVALID_SECRET},
    )
    assert failed.status_code == 401
    assert failed.json() == {"detail": "invalid credentials"}
    assert failed.headers["www-authenticate"] == "Bearer"
    assert failed.headers["cache-control"] == "no-store"
    assert credential.failed_attempts == 1

    success = client.post(
        "/auth/login",
        json={"email": "LOGIN@example.test", "password": TEST_SECRET},
    )
    assert success.status_code == 200
    session_token = SessionTokenResponse.model_validate(success.json())
    assert session_token.user_id == registered.user_id
    assert session_token.access_token != registered.access_token
    assert credential.failed_attempts == 0
    assert credential.locked_until is None


def test_current_user_and_logout_revoke_only_current_session(app_db_session: Session) -> None:
    client = TestClient(app)
    first = _register(client, email="logout@example.test")
    second_response = client.post(
        "/auth/login",
        json={"email": "logout@example.test", "password": TEST_SECRET},
    )
    assert second_response.status_code == 200
    second = SessionTokenResponse.model_validate(second_response.json())

    first_headers = {"Authorization": f"Bearer {first.access_token}"}
    second_headers = {"Authorization": f"Bearer {second.access_token}"}

    me = client.get("/auth/me", headers=first_headers)
    assert me.status_code == 200
    current = CurrentUserResponse.model_validate(me.json())
    assert current.id == first.user_id
    assert current.email == "logout@example.test"

    logout = client.post("/auth/logout", headers=first_headers)
    assert logout.status_code == 204
    assert logout.content == b""

    revoked = client.get("/auth/me", headers=first_headers)
    assert revoked.status_code == 401

    still_active = client.get("/auth/me", headers=second_headers)
    assert still_active.status_code == 200
    assert CurrentUserResponse.model_validate(still_active.json()).id == first.user_id
