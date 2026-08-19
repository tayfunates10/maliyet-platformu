# ADR 0016 — Explicit engine registry and execution boundary

## Status

Accepted.

## Context

The platform now has eight sector calculation keys and tamper-evident
`CalculationVersion` persistence. A caller must never be able to choose a Python
module path, function name, import target, or executable expression. The HTTP
layer also does not yet have an authenticated actor context, so exposing a
state-changing execution endpoint would let a caller spoof tenant/user identity.

## Decision

1. Engine selection uses one closed registry keyed by:
   `food_manufacturing`, `textile_manufacturing`, `basic_metals`, `ecommerce`,
   `trade`, `transportation`, `accommodation`, and `tourism`.
2. `trade` and `ecommerce` remain separate logical keys while sharing the same
   commerce engine implementation/version.
3. Continuous quantities, rates and money cross the JSON contract as strings.
   The execution boundary converts them to finite `Decimal`; JSON floats are
   rejected by strict Pydantic contracts.
4. Unknown fields are rejected. Domain validation remains authoritative after
   transport validation.
5. Registered execution produces canonical input, ruleset and output snapshots
   and can persist only through `record_calculation_version`.
6. Current regulatory rules are not silently resolved by sector management-cost
   engines. Their ruleset snapshot explicitly records that no regulatory rules
   were applied.
7. Public HTTP exposes only engine catalog and input-schema discovery until an
   authenticated actor/tenant context exists.
8. No public endpoint accepts `actor_user_id`, arbitrary import paths, dynamic
   callables, expressions or code.

## Consequences

- Adding a new engine requires a reviewed registry entry and a typed contract.
- API clients receive machine-readable schemas without learning executable
  implementation targets.
- Historical calculation provenance stays aligned with the logical engine key.
- State-changing execution will be added only after authentication and
  authorization establish the trusted actor context.
