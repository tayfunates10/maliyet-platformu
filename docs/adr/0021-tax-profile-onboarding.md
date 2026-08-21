# ADR 0021: Declared tax-profile onboarding and authorization

- **Status:** Accepted
- **Date:** 2026-08-21

## Context

Organization onboarding now establishes a tenant, but regulated calculations also need tenant-declared taxpayer context. The existing `TaxProfile` table contains only `entity_type` and `vat_registered`; it intentionally contains no tax rates, thresholds or formulas.

This boundary is legally sensitive. The Ministry of Trade's current company information distinguishes statutory company forms such as anonim, limited, kollektif, komandit and kooperatif. The existing application `entity_type` vocabulary is coarser and also includes categories such as `sole_proprietorship` and `partnership`. Therefore `entity_type` must **not** be represented as an authoritative statutory legal-form taxonomy.

Official references reviewed for this decision:

- Ministry of Trade, company information: <https://ticaret.gov.tr/ic-ticaret/sirketler/sirket-bilgiler>
- Revenue Administration, Katma Değer Vergisi Kanunu including taxpayer provisions: <https://www.gib.gov.tr/mevzuat/kanun/436>

## Decision

### Declared context only

`TaxProfile` records tenant-declared application context:

- `entity_type` from the existing application allowlist;
- `vat_registered` as an explicit strict JSON boolean declaration.

It does not contain or imply:

- a statutory company-form determination;
- a VAT rate;
- an income/corporate tax rate;
- a withholding rate;
- a tax bracket or monetary threshold;
- an exemption or incentive conclusion.

All rates, thresholds, legal sources and effective dates remain the responsibility of the versioned rules engine and calculation snapshot.

### Authorization

Tax context is internal business configuration:

- `owner` and `admin` may create/update it;
- `accountant` may read it;
- `analyst` and `viewer` may not read or write it;
- non-members fail closed before profile existence is disclosed.

The authenticated user and organization membership are resolved exclusively from server-side session/membership state. Request bodies cannot select an actor, role or organization.

### API semantics

- `POST /organizations/{organization_id}/tax-profile` creates the single profile and returns 409 when one already exists.
- `GET /organizations/{organization_id}/tax-profile` returns the current profile to an authorized reader and 404 only after authorization succeeds.
- `PUT /organizations/{organization_id}/tax-profile` updates an existing profile and returns 404 when an authorized tenant has not created one yet.
- Request payloads use `extra=forbid`, so fields such as `tax_rate`, actor IDs or role overrides are rejected.
- `vat_registered` is strict: strings and numeric stand-ins such as `"yes"`, `1` or `0` are rejected with 422 rather than coerced.

### Auditability and concurrent mutation

Creation writes `tax_profile.created`.
Updates write `tax_profile.updated` with explicit `before` and `after` declared context.
The audit event is in the same request transaction as the profile mutation.

An update must acquire a PostgreSQL row-level `FOR UPDATE` lock on the current `TaxProfile` before the `before` snapshot is captured. Concurrent owner/admin updates are therefore serialized. This prevents a later writer from recording a stale `before` state or silently overwriting another committed change while producing a discontinuous audit chain.

## Consequences

- The coarse `entity_type` vocabulary can be used only as declared application context until a separately reviewed statutory legal-form taxonomy is introduced.
- No tax computation may branch on this field as though it were a complete legal determination without an explicit rules-engine mapping and official-source review.
- Tax-profile boolean declarations are fail-closed at the HTTP schema boundary.
- Concurrent updates preserve adjacent audit-state continuity through row locking.
- There is no schema migration in this PR because the existing table already supports the declared-context boundary.

## Deferred

- Normalized statutory legal-form taxonomy/codes.
- Taxpayer registration identifiers and verification workflows.
- VAT exemption/special-regime declarations.
- Effective-dated TaxProfile history beyond immutable audit events.
- SMMM/YMM review workflow.
- Any actual tax rate, threshold, exemption or filing calculation.
