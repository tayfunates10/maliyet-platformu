# ADR 0029 — Investment and Scenario Calculation Core

## Status

Accepted for PR #35.

## Context

The canonical first-release scope requires capital decision support with ROI, ROE, ROIC and pessimistic/normal/optimistic scenarios. These metrics are easy to make misleading if the engine silently invents tax rates, financing mix, inflation, discount rates, or scenario shocks.

The existing repository contract also requires Decimal-only monetary/rate calculations and reproducible snapshots.

## Decision

A sector-neutral `investment_scenario_engine` provides two explicit primitives:

1. Investment ratios from caller-supplied numerators and denominators.
2. A canonical three-case scenario comparison from caller-supplied revenue and cost amounts.

### Investment ratios

- ROI = explicit `net_return / initial_investment`.
- ROE = explicit `net_income / equity`.
- ROIC = explicit `net_operating_profit_after_tax / invested_capital`.
- All three denominators must be positive.
- Return/profit numerators may be negative so losses are preserved.
- NOPAT is an explicit upstream input; this engine does not derive it from a tax rate.

### Scenario set

The only canonical keys are:

- `pessimistic`
- `normal`
- `optimistic`

Each case carries explicit revenue and costs for the same period and currency context. The engine does not generate percentage shocks. It computes profit and profit margin, preserves losses, returns no fabricated margin when revenue is zero, and validates `pessimistic <= normal <= optimistic` by profit to catch mislabeled comparisons.

### Numeric and policy boundary

- Financial values must be finite Python `Decimal` values.
- Binary float input fails closed.
- No hidden rounding is performed.
- The deterministic snapshot serializes Decimal values as strings.
- The snapshot explicitly records that tax rate, financing mix, inflation, discount rate and scenario shocks were not inferred.

## Consequences

This PR establishes management decision primitives, not a valuation or statutory accounting engine. Future DCF/NPV/IRR work must introduce explicit period cash flows and a caller-supplied discount-rate policy rather than silently extending these formulas.

The engine is not yet registered as one of the eight sector execution keys; it is a cross-sector decision-support primitive that can later be composed with persisted calculation results and web workflows.

## Rejected alternatives

### Hard-coded pessimistic/optimistic percentages

Rejected because no universal percentage is authoritative and hidden shocks would make historical results non-reproducible.

### Derive ROIC NOPAT from accounting profit and a default tax rate

Rejected because applicable tax treatment is entity/date/rule dependent and belongs to the source-backed rules layer.

### Convert Decimal values to float for ratio presentation

Rejected because it violates the repository financial precision contract.
