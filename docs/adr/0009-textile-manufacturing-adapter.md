# ADR 0009 — Textile manufacturing adapter

## Status

Accepted for PR #10.

## Context

The common manufacturing core can price arbitrary materials and conversion costs, but textile production needs domain semantics that must not corrupt physical units. Fabric may be measured in metres, yarn in kilograms, accessories in pieces, while yield is usually evaluated in finished-piece counts. Adding those physical quantities together would fabricate a meaningless yield basis.

Textile production also has stage semantics such as cutting, sewing, dyeing, finishing, printing, embroidery and quality control. These stage labels are useful for management reporting, while the common manufacturing core still needs an explicit cost category such as labor, machine, energy, quality or subcontracting.

## Decision

1. Textile material lines keep their original measurement unit and are costed only as `quantity × unit_cost`.
2. Fabric, yarn, accessories, lining, chemicals and packaging are never physically summed.
3. Yield is calculated only from theoretical finished-piece count versus good finished-piece count.
4. Cutting rejects and quality rejects remain separate integer counts.
5. Ordered pieces may be less than good pieces; the difference is reported as surplus good output.
6. Ordered pieces may never exceed good output.
7. Textile process lines carry two independent classifications:
   - textile process stage for management semantics;
   - common manufacturing cost category for cost aggregation.
8. Scrap/recovery value is accepted only as an explicit monetary `RecoveryCredit`; the adapter does not invent a recovery price.
9. Finished-piece unit cost is the common manufacturing net batch cost divided by good piece count.
10. `management_order_cost` is explicitly a management allocation (`unit_cost × ordered_piece_count`), not a legal inventory valuation.
11. Binary float inputs are rejected; all monetary/material quantity values use `Decimal`.
12. No tax waste policy, inventory valuation policy, or textile-specific legal rule is implied by the adapter.

## Consequences

- Metres, kilograms and pieces cannot be accidentally mixed into a fake physical yield.
- Process-stage profitability remains visible without duplicating the common manufacturing calculation engine.
- Surplus good output is explicit instead of silently charging the full batch to an order.
- Legal inventory valuation and tax treatment remain future source-backed layers.

## Follow-up

After this adapter is green and merged, the next manufacturing sector adapter is basic metals, including metal charge/material usage, melt/process loss, energy/furnace process costs and explicit recovered-scrap credit semantics.
