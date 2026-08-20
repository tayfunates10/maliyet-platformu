# ADR 0018: Tenant-scoped calculation lifecycle API and regression hardening

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

ADR 0017 established authenticated actor identity and tenant-scoped execution, but callers still lacked an HTTP lifecycle for creating calculations and reading calculation/version history. During PR #17 and PR #18, several CI failures also exposed preventable test-infrastructure drift:

- an Alembic revision identifier exceeded the default `alembic_version.version_num VARCHAR(32)` capacity;
- a hand-maintained expected-table set became stale after a new table was introduced;
- a FastAPI database dependency override returned a generator object instead of registering a generator dependency;
- an HTTP JSON UUID string was compared directly with a Python `UUID` object.

These are process defects that should be prevented by reusable contracts rather than rediscovered in later PRs.

## Decision

### Calculation lifecycle

The authenticated tenant boundary now exposes:

- `POST /organizations/{organization_id}/calculations`
- `GET /organizations/{organization_id}/calculations`
- `GET /organizations/{organization_id}/calculations/{calculation_id}`
- `GET /organizations/{organization_id}/calculations/{calculation_id}/versions`
- `GET /organizations/{organization_id}/calculations/{calculation_id}/versions/{version_number}`

Creation requires one of the calculation-write roles (`owner`, `admin`, `accountant`, `analyst`). `viewer` remains read-only. Every route resolves membership from the authenticated server-side identity before tenant data is queried.

A new calculation type must already exist in the closed engine registry. Caller-controlled arbitrary engine keys therefore cannot create logical calculations.

Calculation creation records an append-only `calculation.created` audit event with the authenticated actor. Version history is never recalculated on read; the API returns the immutable snapshots already persisted by the orchestration boundary.

List endpoints are bounded to at most 100 records per request and use stable ordering.

### Regression hardening

PostgreSQL/Alembic tests now enforce the following repository contracts:

1. Alembic revision IDs must be unique and no longer than 32 characters.
2. Migration history must have exactly one head.
3. Expected application tables are derived from SQLAlchemy `Base.metadata`; new models cannot require a manually maintained table-name list.
4. Full `upgrade -> downgrade -> upgrade` and metadata drift tests remain mandatory on real PostgreSQL.
5. FastAPI database dependency overrides use one shared pytest fixture that yields the real transaction-bound `Session` through FastAPI's generator dependency protocol.
6. HTTP integration tests validate JSON through typed Pydantic response models before comparing UUID values or other typed fields.

### CI execution discipline

The repository already uses GitHub Actions concurrency with `cancel-in-progress: true`. Development changes should therefore be batched into cohesive commits where possible so only the latest PR head consumes the full CI pipeline.

## Security consequences

- Membership is established before any calculation list/detail/version query.
- Cross-tenant reads fail closed with HTTP 403.
- Cross-tenant resource identifiers cannot be used to infer private calculation content.
- Viewer identities cannot create calculations or execute engines.
- Calculation creators and audit actors come only from authenticated server-side identity.
- Version history exposes private snapshots only to members of the owning organization.

## Data and regulatory consequences

This ADR does not add or change any statutory rate, threshold or tax formula. Existing effective-date/versioned rules and immutable ruleset snapshots remain authoritative.

## Deferred

- Calculation rename/archive/delete lifecycle.
- Search/filter APIs beyond bounded pagination.
- Fine-grained permissions below organization membership roles.
- Public/widget-safe projection endpoints.
- Service-account/API-client authentication.
