# ADR 0022: Customer-safe public calculation projection boundary

- **Status:** Accepted
- **Date:** 2026-08-21

## Context

Internal calculation versions intentionally persist complete immutable input, ruleset and output snapshots for auditability. Those snapshots include commercially sensitive material such as material/acquisition costs, supplier context, operating costs, contribution profit and margin data.

The product also needs website widgets, public quote links and API integrations. Returning an internal snapshot and trying to redact fields at request time would make every new engine field a potential data leak. The safe default must therefore be fail-closed.

## Decision

### Separate publication artifact

A customer-visible result is a separate `PublicCalculationProjection` record. It references exactly one immutable `CalculationVersion`, but it does **not** copy or expose:

- `input_snapshot` or `input_sha256`;
- `ruleset_snapshot` or `ruleset_sha256`;
- `output_snapshot` or `output_sha256`;
- organization, calculation, version or creator identifiers;
- costs, profit, margin, supplier data or other internal engine fields.

The first public envelope contains only:

- customer-facing title;
- three-letter currency code;
- minimum estimate;
- maximum estimate;
- publication timestamp.

The estimate envelope is presentation data approved for customer visibility. It is not a tax calculation and does not replace the authoritative server-side calculation engine. Automated target-price derivation can be added later only through a separately reviewed pricing engine/projector.

### Complete provenance source only

Publication is allowed only when the source `CalculationVersion` has non-null input, ruleset and output SHA-256 provenance digests. Draft/incomplete versions fail closed.

The database adds a composite `(id, organization_id)` unique key to calculation versions and uses it as the public projection foreign-key target. A projection therefore cannot reference a version belonging to a different tenant even if application filtering is bypassed.

### Publication authorization

Only `owner` and `admin` memberships may publish or revoke customer-visible artifacts. `accountant`, `analyst`, `viewer` and non-members are denied. The actor is resolved from the authenticated server-side session and membership; request bodies cannot choose the publisher identity or role.

### Opaque share tokens

Publication generates a high-entropy opaque token. The raw token is returned only once in the authenticated creation response. Persistence stores only its SHA-256 digest.

Anonymous reads resolve the token digest and return only the fixed public response model. Invalid, unknown, oversized and revoked tokens return the same 404 response.

### Immutable and revocable

A public projection is immutable after creation. A changed customer estimate requires a new projection. Existing projections may only be revoked. Revocation is idempotent, audited and immediately respected by anonymous reads.

Creation and public reads use `Cache-Control: no-store` so share tokens and revocation-sensitive content are not intentionally cached by the application contract.

### Exact monetary transport

Public estimate inputs are strict decimal strings. Binary floating-point inputs are rejected. Persistence uses PostgreSQL `NUMERIC(38,12)` with non-negative and ordered-range constraints. The API returns decimal strings.

## Consequences

- Adding a new private field to an engine cannot make it public automatically.
- Public response schema expansion requires an explicit code and review change.
- Widgets and public quote links can consume a safe server-side artifact without receiving internal calculation snapshots.
- Raw share tokens cannot be recovered from the database.
- Revocation does not delete historical audit evidence.
- No tax rate, threshold or formula is introduced by this ADR.

## Deferred

- CDN/gateway alias from the internal `/organizations/public/...` route to a dedicated public hostname/path.
- Widget SDK and allowed-domain enforcement.
- API-key/OAuth publication clients.
- Automatically derived target/minimum/recommended prices from a reviewed pricing engine.
- Lead capture, quote acceptance and CRM webhook flows.
- White-label presentation and tenant branding.
