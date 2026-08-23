# ADR 0030 — Tenant-scoped investment and scenario API

## Status

Accepted.

## Context

The investment/scenario engine is deterministic and Decimal-only, but the SaaS application needs an authenticated HTTP boundary before it can consume ROI, ROE, ROIC and explicit pessimistic/normal/optimistic outcomes. The boundary must not weaken tenant isolation or allow JSON numbers to enter the financial engine.

## Decision

Expose `POST /organizations/{organization_id}/decision-analysis/investment-scenarios` through the existing organization router.

The endpoint:

- requires an active opaque bearer session;
- resolves organization membership server-side before calculation;
- accepts every monetary value as a strict JSON string and converts it to finite `Decimal` only at the adapter boundary;
- accepts exactly three explicitly named scenarios and never generates percentage shocks;
- delegates all financial calculations and deterministic ratio policy to `investment_scenario_engine`;
- returns the engine-owned deterministic snapshot, including policy flags;
- does not persist the request or result in this first adapter PR.

Viewer members may use the endpoint because it is a stateless tenant-private calculation with no mutation. Cross-tenant requests fail closed.

## Consequences

The web application can consume the decision-support engine without duplicating formulas in the browser. A later PR may add an explicit persisted decision-analysis lifecycle; persistence must preserve immutable input/output provenance rather than silently overwriting prior analyses.

This API does not infer tax rates, financing mix, inflation, discount rates, or scenario shocks, and it does not change public/widget projection boundaries.
