# ADR 0020: Authenticated organization onboarding

- **Status:** Accepted
- **Date:** 2026-08-21

## Context

PR #20 gives a user an authenticated identity, but an authenticated user still needs a safe way to establish a tenant before creating calculations. `Organization`, `OrganizationMembership` and `BusinessProfile` already exist, so onboarding does not require a new schema. The security-sensitive question is who chooses the first owner and whether a partially-created tenant can escape a failed bootstrap.

## Decision

### Server-assigned owner

`POST /organizations` accepts only business bootstrap data:

- slug;
- legal name;
- primary sector;
- optional city.

It does **not** accept `owner_user_id`, creator ID, role, membership list or arbitrary country. The authenticated identity is always inserted as the first `owner` membership by the server.

### Atomic bootstrap

Organization creation, owner membership, initial `BusinessProfile` and `organization.created` audit event are one request transaction. A duplicate slug or validation failure must not leave a partial organization, membership or profile.

The initial country context is `TR`. `TaxProfile` is deliberately not created in this PR because taxpayer entity type and VAT status have legal/accounting meaning and require their own validated onboarding flow.

### Sector validation

`primary_sector` must be one of the repository's locked `SUPPORTED_SECTORS`. The API does not invent or silently map unknown sectors.

### Slug policy

The canonical organization slug is explicit lowercase kebab-case: 3-80 characters, lowercase ASCII letters/numbers with single internal hyphens. The server validates rather than silently transliterating or generating a different slug.

### Read boundary

- `GET /organizations` lists only memberships of the authenticated user and is bounded to at most 100 records per request.
- `GET /organizations/{organization_id}` resolves membership before returning organization/profile data.
- A non-member receives HTTP 403; the endpoint does not leak another tenant's profile.
- Legacy organizations that do not yet have a `BusinessProfile` remain readable with nullable profile fields rather than crashing the listing path.

## Audit and tenant consequences

- The first membership always comes from authenticated server state.
- `organization.created` records the authenticated actor after the owner membership exists, satisfying the audit actor foreign key.
- Calculation tenant boundaries introduced earlier are unchanged.
- Login alone does not grant access to any existing organization.

## Deferred

- TaxProfile/entity-type onboarding.
- Additional sector activations beyond the primary sector.
- Inviting additional members and changing roles.
- Organization rename/archive/delete.
- Slug-change workflow.
- Subscription/payment bootstrap.

Each deferred capability requires its own authorization and audit contract.
