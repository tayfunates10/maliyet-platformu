# ADR 0013 — Accommodation room-night costing

## Status

Accepted for PR #14.

## Context

Accommodation profitability needs a capacity model rather than a simple revenue-minus-expense total. Available room-nights, occupied room-nights, channel-specific revenue, channel commission, occupancy-driven service cost and period-fixed cost all affect unit economics differently.

Channel commission schedules and tax treatment also vary by provider, contract and date. The room-cost kernel must not hard-code OTA commission rates, accommodation-tax rates, VAT treatment or occupancy forecasts.

## Decision

1. Available room-night capacity is `available_rooms_per_night × nights`.
2. Occupied room-nights are explicit and may not exceed available room-nights.
3. Channel sale room-nights must reconcile exactly to occupied room-nights.
4. Each channel sale carries explicit gross room revenue and explicit revenue reductions.
5. Percentage channel commission always carries both explicit `commission_base_amount` and explicit `commission_rate`; the base is never inferred from gross/net room revenue.
6. Fixed channel fees are separate from percentage commission.
7. Costs carry both a category and a management scope:
   - `occupied_variable` for occupancy-driven period cost;
   - `period_fixed` for period-level cost.
8. The engine reports occupied-variable cost, period-fixed cost and total operating cost separately.
9. Cost per occupied room-night is unavailable when occupancy is zero rather than fabricated.
10. Cost per available room-night is always defined because room-night capacity must be positive.
11. Net room revenue per occupied and available room-night is reported separately.
12. Accommodation contribution is net room revenue after explicit channel fees minus total operating cost.
13. Losses remain negative and are never clamped.
14. Monetary math uses `Decimal`; binary floats fail closed.
15. The engine does not apply or infer accommodation tax, VAT, channel fee schedules, occupancy forecasts or inventory/accounting policy.
16. Total accommodation operating cost can be bridged into the sector-neutral costing core as a `CostLine`.

## Consequences

- Occupancy and capacity cannot silently diverge from channel sales.
- OTA/direct-channel economics remain auditable because commission base and rate are explicit.
- Zero-occupancy periods are handled safely while fixed costs remain visible.
- Tax and legal accounting rules can be attached later through the versioned rules engine instead of being mixed into room operations.

## Follow-up

After this engine is green and merged, tourism package costing will model transport, accommodation, guide, transfer, meals, tickets, activities, insurance and channel/agency fees with explicit package quantity and currency-context boundaries.
