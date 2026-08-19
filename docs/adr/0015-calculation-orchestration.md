# ADR 0015 — Calculation version orchestration and replay provenance

## Status

Accepted for PR #16.

## Context

The platform already stores tenant-owned `Calculation` and `CalculationVersion` rows with input, ruleset and output JSON snapshots. Tenant ownership is protected at the database boundary through composite foreign keys. The missing production boundary is reproducibility: a historical calculation version must identify the exact engine contract used, preserve its rule provenance, detect later snapshot drift and allocate version numbers safely when multiple writes target the same logical calculation.

Historical replay must also remain independent of whatever tax/accounting rules are current when the record is reopened. Re-resolving today's rules would make an old result silently change.

## Decision

1. New production calculation-version writes use `record_calculation_version`; the older low-level tenancy helper remains backward-compatible for legacy/tests but does not provide replay provenance.
2. `Calculation.calculation_type` is the logical engine key for the calculation. A new version may be recorded only when its `engine_key` exactly matches that calculation type.
3. Every newly orchestrated version stores both `engine_key` and `engine_version`.
4. Input, ruleset and output snapshots are validated as JSON-compatible values. Binary floats and unsupported Python objects fail closed. Monetary Decimal values must already be serialized as deterministic strings by the domain engine snapshot layer.
5. Snapshots are canonicalized with sorted JSON keys and compact UTF-8 JSON, then SHA-256 digested independently as `input_sha256`, `ruleset_sha256` and `output_sha256`.
6. Canonicalization deep-copies the caller data before persistence so later mutation of request/application dictionaries cannot mutate the persisted snapshot through object aliasing.
7. The target `Calculation` row is tenant-scoped and locked with `SELECT ... FOR UPDATE` before the next version number is selected. This serializes version-number allocation per logical calculation.
8. The next version number is `max(existing version) + 1` while the calculation row lock is held. The existing database unique constraint on `(calculation_id, version)` remains a second boundary.
9. The actor must be a member of the same organization. Cross-tenant calculations and versions are exposed as not found.
10. Recording a version also appends an `AuditEvent` containing calculation id, version, engine identity and the three snapshot hashes.
11. `load_replay_material` reads only the stored historical engine identity and stored input/ruleset/output snapshots. It does not query or resolve current rules.
12. Replay verifies all three hashes before returning material. Any missing provenance or digest mismatch fails closed.
13. Existing legacy rows are not backfilled with fabricated engine keys or fake hashes. Migration columns are nullable so old data remains representable, but replay refuses provenance-incomplete rows.
14. This design is **tamper-evident and append-only by service contract**, not physically immutable storage. Direct database mutation can be detected by hashes but is not prevented by a database trigger in this PR.
15. No DELETE-blocking trigger is introduced because organization/account deletion and future KVKK retention workflows require a deliberate lifecycle design.
16. This PR does not execute arbitrary engine names from persisted JSON. Engine dispatch/registry and API exposure are separate layers.

## Integrity boundary

For a newly orchestrated version, reproducible historical material consists of:

- organization id and calculation id;
- monotonic calculation version number;
- engine key and engine version;
- canonical input snapshot and SHA-256;
- canonical ruleset/provenance snapshot and SHA-256;
- canonical output snapshot and SHA-256;
- audit event linking the actor and version.

A replay is valid only when all required provenance exists and every digest matches its stored snapshot.

## Consequences

- Opening a historical calculation no longer requires resolving today's rules.
- Silent snapshot mutation becomes detectable.
- Concurrent writers targeting the same logical calculation share a row-lock serialization point.
- Legacy rows remain readable at the database level but cannot be represented as verified replay material without genuine provenance.
- Future engine registry/API/UI layers can build on one stable persistence contract.

## Follow-up

The next PR should introduce an explicit engine registry/dispatch boundary and API request contracts that map supported sector calculation types to deterministic engine functions, then persist successful runs through this orchestration layer. No client should be allowed to select arbitrary import paths or executable code as an engine.
