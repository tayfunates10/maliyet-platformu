# ADR 0014 — Tourism package costing

## Status

Accepted for PR #15.

## Context

Tourism-package profitability combines participant-driven costs such as hotel, meals, tickets and insurance with package-level fixed costs such as transport, guide or transfer. Revenue may arrive through direct and agency/channel sales, each with different explicit fees.

Tourism also frequently involves multiple currencies. Silently combining TRY, EUR and USD would make the calculation invalid. FX conversion must therefore be performed by a separate explicit layer before values enter this core.

## Decision

1. Every calculation has one explicit currency context and all monetary inputs must already be normalized into that currency.
2. The engine never fetches or infers FX rates and never mixes multiple currency contexts.
3. Package participant count must be a positive integer.
4. Channel participant totals must reconcile exactly to the package participant count.
5. Channel revenue keeps gross revenue, explicit reductions, explicit commission base/rate and fixed channel fee separate.
6. Percentage agency/channel commission is always `explicit base × explicit rate`; the base is never inferred.
7. Package components use one of two scopes:
   - `per_participant`: amount is multiplied by participant count;
   - `fixed_package`: amount is charged once to the package.
8. Supported management categories are transportation, accommodation, guide, transfer, meal, ticket, activity, insurance and other.
9. Total package cost, cost per participant, net revenue per participant, package contribution and contribution per participant are calculated with exact `Decimal` arithmetic.
10. Losses remain negative and contribution margin is unavailable rather than fabricated when net revenue after channel fee is zero.
11. Duplicate line keys across channels and components fail closed.
12. The total package cost can be bridged into the sector-neutral costing core as a `CostLine`.
13. The snapshot explicitly states that FX conversion/rates, agency fee schedules, tourism tax, VAT and travel-package legal policy were not inferred/applied.

## Consequences

- Per-participant and fixed package economics cannot silently contaminate each other.
- Agency commission assumptions are auditable because both base and rate are explicit.
- Multi-currency inputs must be normalized before calculation, preventing invalid cross-currency totals.
- Tax, VAT, FX and legal travel-package treatment can be layered later without changing the management-cost kernel.

## Follow-up

After this engine is green and merged, the initial sector calculation-kernel milestone is complete. The next milestone is calculation orchestration and persistence: connect tenant-owned calculations to engine input/output snapshots, rule versions and reproducible calculation versions before exposing full sector forms in the web application.
