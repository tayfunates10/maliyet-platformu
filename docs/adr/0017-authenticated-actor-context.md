# ADR 0017: Authenticated actor context and tenant write authorization

- **Status:** Accepted
- **Date:** 2026-08-19

## Context

ADR 0016 intentionally exposed only engine discovery over public HTTP. Stateful calculation execution was blocked until the API could establish actor identity independently of caller-supplied JSON and bind that identity to an organization membership.

The platform is multi-tenant and stores private business costs, margins and calculation history. A request must therefore be authenticated before tenant authorization is evaluated, and a caller must never be able to provide `actor_user_id`, membership role, import path or execution target as trusted input.

## Decision

### Opaque server-side sessions

- Bearer credentials are high-entropy opaque tokens.
- Only a SHA-256 digest of the token is persisted in `auth_sessions`; raw bearer tokens are never stored.
- Sessions have explicit expiry and revocation timestamps.
- Authentication additionally requires the referenced `User` to remain active.
- Session issuance is an internal primitive in this stage. There is no anonymous login/session-issuance HTTP endpoint yet.

### Actor and tenant binding

Authentication yields only `AuthenticatedIdentity(user_id)` from the server-side session. For a tenant-scoped request, `organization_memberships` is then queried using that authenticated user ID and the organization ID from the route.

The resulting `ActorContext` contains:

- authenticated `user_id`;
- route-bound `organization_id`;
- server-side membership `role`.

The calculation-write policy permits `owner`, `admin`, `accountant` and `analyst`. `viewer` is read-only and receives HTTP 403 for execution attempts. A user with no membership in the requested organization also receives HTTP 403.

### Stateful execution endpoint

`POST /organizations/{organization_id}/calculations/{calculation_id}/execute/{engine_key}` is the first state-changing calculation execution endpoint.

Execution order is fail-closed:

1. validate bearer session;
2. resolve organization membership;
3. enforce calculation-write role;
4. resolve the calculation inside the same organization;
5. require route engine key to match the calculation type;
6. execute only the ADR 0016 closed engine registry;
7. persist through the ADR 0015 orchestration layer using the authenticated actor ID;
8. return immutable provenance digests and the output snapshot.

The request body is only the engine payload. Unknown fields such as `created_by_user_id` are rejected by the strict engine contract; actor identity is never selected from the payload.

### Request transaction

Database-backed HTTP requests use one SQLAlchemy session per request. The dependency commits only after the successful endpoint path, rolls back on exceptions, and always closes the session.

## Security consequences

- Raw bearer credentials do not exist in persistent storage.
- Revocation and expiry are server-controlled.
- Cross-tenant membership is checked before calculation lookup/execution.
- Viewer accounts cannot mutate calculation history.
- Existing database tenant foreign keys and append-only provenance remain the final persistence boundary.
- Dynamic imports, `eval`, `exec`, reflection-based callable selection and caller-controlled actor IDs remain prohibited.

## Deferred

- Password login and password-reset flows.
- OAuth/OIDC/SSO provider integration.
- Refresh-token rotation and device/session management UI.
- MFA/2FA.
- API clients/service accounts for third-party integrations.

These require separate threat models and do not weaken this actor boundary.
