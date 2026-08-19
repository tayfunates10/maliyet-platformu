# ADR 0011 — Trade and e-commerce order economics

## Status

Accepted for PR #12.

## Context

Trade and e-commerce share the same product economics but add channel-specific costs such as marketplace commission, payment/POS charges, fulfillment, storage, packaging, advertising and returns. These charges are not universal: the same nominal percentage can be calculated from different monetary bases depending on provider, contract, date and transaction type.

Hard-coding a marketplace or payment-provider schedule would violate the platform rules-engine boundary and create silent mispricing. Return behavior also differs by business; neither a return probability nor the recoverable inventory value can be guessed safely.

## Decision

1. Gross sales are explicit quantity × unit sale price.
2. Discounts and return allowance are explicit management revenue reductions and may not exceed gross sales.
3. Acquisition cost is quantity × explicit unit acquisition cost.
4. Returned/recovered inventory value is an explicit monetary credit and may not exceed gross acquisition cost.
5. Operating costs are explicit allocated amounts grouped as inbound freight, fulfillment, packaging, storage, advertising, return handling or other.
6. Percentage fees always contain both an explicit monetary `base_amount` and an explicit `rate`; the engine never infers the base from gross or net sales.
7. Fixed marketplace/payment/channel charges are separate from percentage fees.
8. Fee schedules are not hard-coded and no provider-specific commission rate is assumed.
9. Contribution profit is management economics before VAT, income/corporate tax and legal inventory valuation policy.
10. Zero net sales produces no fabricated contribution-margin percentage.
11. Losses remain negative; they are never clamped to zero.
12. Monetary and continuous quantity calculations use `Decimal`; binary floats fail closed.
13. No return probability is inferred. A caller may supply an explicit return allowance based on its own data or later source-backed modules.

## Consequences

- The same core works for wholesale/retail and e-commerce channels.
- Marketplace and POS fee bases remain auditable instead of hidden in formulas.
- Current/future provider integrations can populate explicit inputs without changing the calculation kernel.
- VAT/tax and inventory accounting can be layered later without contaminating contribution economics.

## Follow-up

After this core is green and merged, transportation costing will add route/sefer economics: distance, loaded/empty kilometres, fuel and AdBlue, toll/ferry costs, driver/assistant labor, maintenance/tyre/depreciation inputs and capacity-based unit economics.
