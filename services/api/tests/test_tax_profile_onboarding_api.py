"""PostgreSQL HTTP tests for tenant-scoped declared tax-profile context."""

from threading import Event, Thread
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.main import SessionTokenResponse, app
from app.models import AuditEvent, Organization, OrganizationMembership, TaxProfile, User
from app.organization_api import OrganizationResponse
from app.tax_profile_api import TaxProfileResponse
from app.tax_profile_onboarding import update_tax_profile

TEST_PASSWORD = "synthetic tax profile credential 2026"


def _register(client: TestClient, *, email: str) -> SessionTokenResponse:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "display_name": "Tax Profile User",
            "password": TEST_PASSWORD,
        },
    )
    assert response.status_code == 201
    return SessionTokenResponse.model_validate(response.json())


def _headers(token: SessionTokenResponse) -> dict[str, str]:
    return {"Authorization": f"Bearer {token.access_token}"}


def _create_org(
    client: TestClient,
    *,
    token: SessionTokenResponse,
    slug: str,
) -> OrganizationResponse:
    response = client.post(
        "/organizations",
        headers=_headers(token),
        json={
            "slug": slug,
            "legal_name": f"{slug} Ltd",
            "primary_sector": "trade",
            "city": "Balikesir",
        },
    )
    assert response.status_code == 201
    return OrganizationResponse.model_validate(response.json())


def _add_member(
    session: Session,
    *,
    organization_id: UUID,
    user_id: UUID,
    role: str,
) -> None:
    session.add(
        OrganizationMembership(
            organization_id=organization_id,
            user_id=user_id,
            role=role,
        )
    )
    session.flush()


def test_owner_can_create_and_read_tax_profile_with_audit(app_db_session: Session) -> None:
    client = TestClient(app)
    owner = _register(client, email="tax-owner@example.test")
    organization = _create_org(client, token=owner, slug="tax-owner-org")

    created_response = client.post(
        f"/organizations/{organization.id}/tax-profile",
        headers=_headers(owner),
        json={"entity_type": "limited", "vat_registered": True},
    )
    assert created_response.status_code == 201
    created = TaxProfileResponse.model_validate(created_response.json())
    assert created.organization_id == organization.id
    assert created.entity_type == "limited"
    assert created.vat_registered is True

    read_response = client.get(
        f"/organizations/{organization.id}/tax-profile",
        headers=_headers(owner),
    )
    assert read_response.status_code == 200
    assert TaxProfileResponse.model_validate(read_response.json()).id == created.id

    audit = app_db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization.id,
            AuditEvent.event_type == "tax_profile.created",
        )
    )
    assert audit is not None
    assert audit.actor_user_id == owner.user_id
    assert audit.payload == {"entity_type": "limited", "vat_registered": True}


def test_tax_profile_rejects_rate_fields_invalid_types_and_duplicates(
    app_db_session: Session,
) -> None:
    client = TestClient(app)
    owner = _register(client, email="tax-validation@example.test")
    organization = _create_org(client, token=owner, slug="tax-validation-org")
    endpoint = f"/organizations/{organization.id}/tax-profile"

    forbidden_rate = client.post(
        endpoint,
        headers=_headers(owner),
        json={
            "entity_type": "limited",
            "vat_registered": True,
            "tax_rate": "0.25",
        },
    )
    assert forbidden_rate.status_code == 422

    for malformed_vat_registered in ("yes", 1, 0):
        malformed = client.post(
            endpoint,
            headers=_headers(owner),
            json={
                "entity_type": "limited",
                "vat_registered": malformed_vat_registered,
            },
        )
        assert malformed.status_code == 422

    assert (
        app_db_session.scalar(
            select(TaxProfile.id).where(TaxProfile.organization_id == organization.id)
        )
        is None
    )

    invalid_type = client.post(
        endpoint,
        headers=_headers(owner),
        json={"entity_type": "statutory-invented-type", "vat_registered": True},
    )
    assert invalid_type.status_code == 422

    first = client.post(
        endpoint,
        headers=_headers(owner),
        json={"entity_type": "limited", "vat_registered": True},
    )
    assert first.status_code == 201

    duplicate = client.post(
        endpoint,
        headers=_headers(owner),
        json={"entity_type": "joint_stock", "vat_registered": False},
    )
    assert duplicate.status_code == 409


def test_admin_can_update_and_change_is_audited(app_db_session: Session) -> None:
    client = TestClient(app)
    owner = _register(client, email="tax-admin-owner@example.test")
    admin = _register(client, email="tax-admin@example.test")
    organization = _create_org(client, token=owner, slug="tax-admin-org")
    _add_member(
        app_db_session,
        organization_id=organization.id,
        user_id=admin.user_id,
        role="admin",
    )

    endpoint = f"/organizations/{organization.id}/tax-profile"
    created = client.post(
        endpoint,
        headers=_headers(owner),
        json={"entity_type": "limited", "vat_registered": True},
    )
    assert created.status_code == 201

    updated_response = client.put(
        endpoint,
        headers=_headers(admin),
        json={"entity_type": "joint_stock", "vat_registered": False},
    )
    assert updated_response.status_code == 200
    updated = TaxProfileResponse.model_validate(updated_response.json())
    assert updated.entity_type == "joint_stock"
    assert updated.vat_registered is False

    audit = app_db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization.id,
            AuditEvent.event_type == "tax_profile.updated",
        )
    )
    assert audit is not None
    assert audit.actor_user_id == admin.user_id
    assert audit.payload == {
        "before": {"entity_type": "limited", "vat_registered": True},
        "after": {"entity_type": "joint_stock", "vat_registered": False},
    }


def test_concurrent_updates_serialize_before_audit_snapshot(db_engine: Engine) -> None:
    with Session(db_engine, expire_on_commit=False) as setup_session:
        user = User(
            email="tax-concurrency-owner@example.test",
            display_name="Tax Concurrency Owner",
        )
        organization = Organization(
            slug="tax-concurrency-org",
            legal_name="Tax Concurrency Organization",
        )
        setup_session.add_all([user, organization])
        setup_session.flush()
        setup_session.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role="owner",
            )
        )
        setup_session.add(
            TaxProfile(
                organization_id=organization.id,
                entity_type="limited",
                vat_registered=True,
            )
        )
        setup_session.commit()
        user_id = user.id
        organization_id = organization.id

    first_locked = Event()
    release_first = Event()
    second_attempting = Event()
    second_finished = Event()
    errors: list[BaseException] = []

    def first_update() -> None:
        with Session(db_engine, expire_on_commit=False) as session:
            try:
                update_tax_profile(
                    session,
                    authenticated_user_id=user_id,
                    organization_id=organization_id,
                    entity_type="joint_stock",
                    vat_registered=False,
                )
                first_locked.set()
                if not release_first.wait(timeout=5):
                    raise AssertionError("timed out waiting to release first tax-profile update")
                session.commit()
            except BaseException as exc:
                errors.append(exc)
                first_locked.set()
                release_first.set()
                session.rollback()

    def second_update() -> None:
        if not first_locked.wait(timeout=5):
            errors.append(AssertionError("first tax-profile update did not acquire its lock"))
            second_finished.set()
            return
        second_attempting.set()
        with Session(db_engine, expire_on_commit=False) as session:
            try:
                update_tax_profile(
                    session,
                    authenticated_user_id=user_id,
                    organization_id=organization_id,
                    entity_type="partnership",
                    vat_registered=True,
                )
                session.commit()
            except BaseException as exc:
                errors.append(exc)
                session.rollback()
            finally:
                second_finished.set()

    first_thread = Thread(target=first_update)
    second_thread = Thread(target=second_update)
    first_thread.start()
    assert first_locked.wait(timeout=5)
    second_thread.start()
    assert second_attempting.wait(timeout=5)
    assert not second_finished.wait(timeout=0.5)

    release_first.set()
    first_thread.join(timeout=5)
    second_thread.join(timeout=5)
    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert not errors, repr(errors)

    with Session(db_engine) as verification_session:
        profile = verification_session.scalar(
            select(TaxProfile).where(TaxProfile.organization_id == organization_id)
        )
        assert profile is not None
        assert profile.entity_type == "partnership"
        assert profile.vat_registered is True

        audits = verification_session.scalars(
            select(AuditEvent).where(
                AuditEvent.organization_id == organization_id,
                AuditEvent.event_type == "tax_profile.updated",
            )
        ).all()
        assert len(audits) == 2
        first_audit = next(
            audit
            for audit in audits
            if audit.payload.get("after") == {"entity_type": "joint_stock", "vat_registered": False}
        )
        second_audit = next(
            audit
            for audit in audits
            if audit.payload.get("after") == {"entity_type": "partnership", "vat_registered": True}
        )
        assert second_audit.payload["before"] == first_audit.payload["after"]


def test_accountant_is_read_only_and_analyst_cannot_read(app_db_session: Session) -> None:
    client = TestClient(app)
    owner = _register(client, email="tax-role-owner@example.test")
    accountant = _register(client, email="tax-accountant@example.test")
    analyst = _register(client, email="tax-analyst@example.test")
    organization = _create_org(client, token=owner, slug="tax-role-org")
    _add_member(
        app_db_session,
        organization_id=organization.id,
        user_id=accountant.user_id,
        role="accountant",
    )
    _add_member(
        app_db_session,
        organization_id=organization.id,
        user_id=analyst.user_id,
        role="analyst",
    )

    endpoint = f"/organizations/{organization.id}/tax-profile"
    created = client.post(
        endpoint,
        headers=_headers(owner),
        json={"entity_type": "sole_proprietorship", "vat_registered": False},
    )
    assert created.status_code == 201

    accountant_read = client.get(endpoint, headers=_headers(accountant))
    assert accountant_read.status_code == 200

    accountant_write = client.put(
        endpoint,
        headers=_headers(accountant),
        json={"entity_type": "limited", "vat_registered": True},
    )
    assert accountant_write.status_code == 403

    analyst_read = client.get(endpoint, headers=_headers(analyst))
    assert analyst_read.status_code == 403


def test_cross_tenant_access_fails_closed_and_missing_profile_is_404(
    app_db_session: Session,
) -> None:
    client = TestClient(app)
    first_owner = _register(client, email="tax-first-owner@example.test")
    second_owner = _register(client, email="tax-second-owner@example.test")
    first_org = _create_org(client, token=first_owner, slug="tax-first-org")
    second_org = _create_org(client, token=second_owner, slug="tax-second-org")

    missing = client.get(
        f"/organizations/{first_org.id}/tax-profile",
        headers=_headers(first_owner),
    )
    assert missing.status_code == 404

    first_created = client.post(
        f"/organizations/{first_org.id}/tax-profile",
        headers=_headers(first_owner),
        json={"entity_type": "limited", "vat_registered": True},
    )
    assert first_created.status_code == 201

    cross_read = client.get(
        f"/organizations/{first_org.id}/tax-profile",
        headers=_headers(second_owner),
    )
    assert cross_read.status_code == 403

    cross_write = client.put(
        f"/organizations/{first_org.id}/tax-profile",
        headers=_headers(second_owner),
        json={"entity_type": "joint_stock", "vat_registered": False},
    )
    assert cross_write.status_code == 403

    second_missing_update = client.put(
        f"/organizations/{second_org.id}/tax-profile",
        headers=_headers(second_owner),
        json={"entity_type": "limited", "vat_registered": True},
    )
    assert second_missing_update.status_code == 404
