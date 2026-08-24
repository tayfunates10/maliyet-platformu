"""Partner API credential lifecycle and tenant-boundary regression tests."""

from hashlib import sha256

import pytest
from sqlalchemy import select

from app.models import AuditEvent, Organization, OrganizationMembership, User
from app.partner_api_credentials import (
    PartnerApiAuthenticationError,
    PartnerApiAuthorizationError,
    authenticate_partner_api_token,
    issue_partner_api_credential,
    revoke_partner_api_credential,
)
from app.partner_api_models import PartnerApiCredential


def _membership(db_session, *, role: str):
    user = User(email=f"{role}@example.test", display_name=role)
    organization = Organization(slug=f"org-{role}", legal_name=f"Org {role}")
    db_session.add_all([user, organization])
    db_session.flush()
    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        role=role,
    )
    db_session.add(membership)
    db_session.flush()
    return user, organization


def test_owner_issues_hash_only_token_and_can_revoke(db_session) -> None:
    user, organization = _membership(db_session, role="owner")

    issued = issue_partner_api_credential(
        db_session,
        organization_id=organization.id,
        created_by_user_id=user.id,
        name="ERP connector",
    )

    assert issued.raw_token.startswith("mp_live_")
    assert issued.raw_token not in str(issued.credential.__dict__)
    assert issued.credential.token_sha256 == sha256(issued.raw_token.encode()).hexdigest()
    assert authenticate_partner_api_token(db_session, raw_token=issued.raw_token).id == issued.credential.id

    stored = db_session.scalar(
        select(PartnerApiCredential).where(PartnerApiCredential.id == issued.credential.id)
    )
    assert stored is not None
    assert stored.token_sha256 != issued.raw_token

    revoke_partner_api_credential(
        db_session,
        organization_id=organization.id,
        credential_id=issued.credential.id,
        revoked_by_user_id=user.id,
    )
    with pytest.raises(PartnerApiAuthenticationError):
        authenticate_partner_api_token(db_session, raw_token=issued.raw_token)

    event_types = set(db_session.scalars(select(AuditEvent.event_type)).all())
    assert "partner_api.credential_issued" in event_types
    assert "partner_api.credential_revoked" in event_types


def test_viewer_cannot_manage_partner_credentials(db_session) -> None:
    user, organization = _membership(db_session, role="viewer")

    with pytest.raises(PartnerApiAuthorizationError):
        issue_partner_api_credential(
            db_session,
            organization_id=organization.id,
            created_by_user_id=user.id,
            name="forbidden",
        )


def test_unknown_and_malformed_tokens_share_generic_failure(db_session) -> None:
    for raw_token in ("bad", "mp_live_unknown"):
        with pytest.raises(PartnerApiAuthenticationError, match="invalid partner API credential"):
            authenticate_partner_api_token(db_session, raw_token=raw_token)
