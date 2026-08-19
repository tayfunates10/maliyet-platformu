# ADR 0010 — Basic-metals manufacturing adapter

## Status

Accepted for PR #11.

## Context

Basic-metals production needs a different physical model from packaged food or finished-piece textile. Raw metal charge, recycled charge, alloy additions, electrodes, fluxes, refractories and other consumables may use different measurement units. Energy may be electricity, gas or another fuel. Treating those heterogeneous inputs as one physical output quantity would fabricate a yield.

The business also needs to see melt loss, slag loss, quality rejection, furnace/energy cost and recovered-scrap value separately.

## Decision

1. Theoretical metal output is an explicit engineering input; it is never inferred by summing material inputs.
2. Melt loss, slag loss and quality rejection must all be supplied in the same output unit as theoretical output.
3. Good output is `theoretical output - explicit losses` and must remain positive.
4. Material lines retain their native units and are costed only as `quantity × unit_cost`.
5. Energy lines retain their native units and are costed as `quantity × unit_rate`; different physical energy units are not added together.
6. Process stages retain metal-process semantics while also carrying a common manufacturing cost category.
7. Recovered scrap is modeled as explicit `quantity × unit_value`; the engine does not infer a market price.
8. The resulting recovered-scrap monetary value is passed to the common manufacturing engine as a recovery credit.
9. All monetary and continuous-quantity math uses `Decimal`; binary floats fail closed.
10. Inventory valuation, tax waste treatment and legal scrap valuation are explicitly out of scope.

## Consequences

- Engineering yield remains physically meaningful.
- Electricity, gas, metal charge and consumables cannot be mixed into fabricated physical totals.
- Scrap recovery improves management cost only when the caller supplies an explicit value.
- Future legal/tax valuation rules can be layered on top without changing the core engineering calculation.

## Follow-up

After this adapter is green and merged, manufacturing-sector coverage for the initial MVP is complete. The next product area is commerce/e-commerce costing and channel fee/commission modeling.
