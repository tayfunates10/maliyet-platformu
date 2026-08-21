"""PostgreSQL HTTP tests for authenticated organization onboarding."""

from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.main import SessionTokenResponse, app
from app.models import AuditEvent, BusinessProfile, Organization, OrganizationMembership
from app.organization_api import OrganizationResponse
from app.organization_onboarding import list_organization_access

TEST_PASSWORD = "synthetic onboarding credential 2026"


def _register(client: TestClient, *, email: str) -> SessionTokenResponse:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "display_name": "Onboarding User",
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
    sector: str = "food_manufacturing",
) -> OrganizationResponse:
    response = client.post(
        "/organizations",
        headers=_headers(token),
        json={
            "slug": slug,
            "legal_name": "  Example Manufacturing Ltd  ",
            "primary_sector": sector,
            "city": "  Balikesir  ",
        },
    )
    assert response.status_code == 201
    return OrganizationResponse.model_validate(response.json())


def test_create_organization_assigns_authenticated_user_as_owner_and_bootstraps_profile(
    app_db_session: Session,
) -> None:
    client = TestClient(app)
    token = _register(client, email="org-owner@example.test")
    created = _create_org(client, token=token, slug="example-food")

    assert created.slug == "example-food"
    assert created.legal_name == "Example Manufacturing Ltd"
    assert created.role == "owner"
    assert created.primary_sector == "food_manufacturing"
    assert created.country_code == "TR"
    assert created.city == "Balikesir"

    membership = app_db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == created.id,
            OrganizationMembership.user_id == token.user_id,
        )
    )
    assert membership is not None
    assert membership.role == "owner"

    profile = app_db_session.scalar(
        select(BusinessProfile).where(BusinessProfile.organization_id == created.id)
    )
    assert profile is not None
    assert profile.primary_sector == "food_manufacturing"

    audit = app_db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == created.id,
            AuditEvent.event_type == "organization.created",
        )
    )
    assert audit is not None
    assert audit.actor_user_id == token.user_id


def test_owner_identity_and_role_are_not_caller_selectable(app_db_session: Session) -> None:
    client = TestClient(app)
    token = _register(client, email="org-extra-fields@example.test")

    response = client.post(
        "/organizations",
        headers=_headers(token),
        json={
            "slug": "forbidden-owner",
            "legal_name": "Forbidden Owner Ltd",
            "primary_sector": "trade",
            "role": "viewer",
            "owner_user_id": "00000000-0000-0000-0000-000000000001",
        },
    )

    assert response.status_code == 422
    assert (
        app_db_session.scalar(select(Organization.id).where(Organization.slug == "forbidden-owner"))
        is None
    )


def test_invalid_sector_and_slug_fail_before_tenant_persistence(app_db_session: Session) -> None:
    client = TestClient(app)
    token = _register(client, email="org-validation@example.test")

    bad_sector = client.post(
        "/organizations",
        headers=_headers(token),
        json={
            "slug": "invalid-sector",
            "legal_name": "Invalid Sector Ltd",
            "primary_sector": "not-a-sector",
        },
    )
    assert bad_sector.status_code == 422

    bad_slug = client.post(
        "/organizations",
        headers=_headers(token),
        json={
            "slug": "Invalid Slug",
            "legal_name": "Invalid Slug Ltd",
            "primary_sector": "trade",
        },
    )
    assert bad_slug.status_code == 422
    assert app_db_session.scalar(select(Organization.id)) is None


def test_list_get_and_duplicate_slug_remain_membership_scoped(app_db_session: Session) -> None:
    client = TestClient(app)
    first = _register(client, email="org-first@example.test")
    second = _register(client, email="org-second@example.test")
    first_org = _create_org(client, token=first, slug="first-org", sector="textile_manufacturing")

    duplicate = client.post(
        "/organizations",
        headers=_headers(second),
        json={
            "slug": "first-org",
            "legal_name": "Duplicate Ltd",
            "primary_sector": "trade",
        },
    )
    assert duplicate.status_code == 409

    second_org = _create_org(client, token=second, slug="second-org", sector="transportation")

    first_list = client.get("/organizations", headers=_headers(first))
    assert first_list.status_code == 200
    first_items = [OrganizationResponse.model_validate(item) for item in first_list.json()]
    assert [item.id for item in first_items] == [first_org.id]

    forbidden = client.get(f"/organizations/{second_org.id}", headers=_headers(first))
    assert forbidden.status_code == 403

    own = client.get(f"/organizations/{second_org.id}", headers=_headers(second))
    assert own.status_code == 200
    assert OrganizationResponse.model_validate(own.json()).id == second_org.id

    second_memberships = app_db_session.scalars(
        select(OrganizationMembership).where(OrganizationMembership.user_id == second.user_id)
    ).all()
    assert len(second_memberships) == 1
    assert second_memberships[0].organization_id == second_org.id


def test_list_organization_access_uses_one_bounded_join_query(app_db_session: Session) -> None:
    client = TestClient(app)
    token = _register(client, email="org-query-count@example.test")
    first = _create_org(client, token=token, slug="query-first", sector="trade")
    second = _create_org(client, token=token, slug="query-second", sector="transportation")

    query_count = 0

    def count_orm_query(_state: object) -> None:
        nonlocal query_count
        query_count += 1

    event.listen(app_db_session, "do_orm_execute", count_orm_query)
    try:
        access = list_organization_access(
            app_db_session,
            authenticated_user_id=token.user_id,
            limit=100,
            offset=0,
        )
    finally:
        event.remove(app_db_session, "do_orm_execute", count_orm_query)

    assert query_count == 1
    assert {item.organization.id for item in access} == {first.id, second.id}
