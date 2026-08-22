# ADR 0023: Widget origin lock and atomic usage boundary

- **Status:** Accepted
- **Date:** 2026-08-21

## Context

PR #23 introduced `PublicCalculationProjection`, an immutable customer-safe publication artifact that is intentionally separate from internal calculation input, ruleset and output snapshots. Website widgets now need a browser-consumption boundary without turning browser-delivered values into fake secrets or weakening tenant isolation.

A browser `Origin` header is useful for controlling which websites may embed a deployment, but it is **not authentication**. A non-browser HTTP client can forge `Origin`. Therefore an allowlisted origin must never grant access to private calculation snapshots, tenant internals or a raw public-projection share token.

Usage limits must also remain correct under concurrent requests. A read-then-write counter would allow quota overruns when two requests race.

## Decision

### Public deployment identity

A widget uses a public `WidgetDeployment.id`. The identifier is not treated as a secret credential. It binds to exactly one already customer-safe `PublicCalculationProjection` inside the same tenant.

The raw share token created by the public-projection boundary is not embedded in widget JavaScript and is not required to consume the widget endpoint.

### Exact-origin registry

Every deployment has one or more explicitly configured allowed origins.

An allowed origin:

- must use HTTPS;
- must be a fully qualified DNS hostname;
- is normalized to lowercase ASCII IDNA form with browser-compatible, non-transitional UTS #46 processing;
- removes the default HTTPS port `443`;
- retains an explicit non-default port;
- must not contain a path, query, fragment, credentials or wildcard;
- must not be an IP literal.

Python's built-in IDNA 2003 codec is not used for this boundary because deviation characters can collapse distinct domains. For example, `faß.de` canonicalizes to `xn--fa-hia.de`; it must never collapse to the distinct ASCII domain `fass.de`.

Matching is exact. Allowing `https://example.com` does not allow `https://sub.example.com`.

`Referer` is not an authorization signal. Missing, `null`, malformed, HTTP, wildcard-equivalent or non-allowlisted origins fail closed.

### Origin is not authentication

The browser-origin check is an embed-control boundary only. Because server clients can forge `Origin`, a successful widget request may return only the already-safe public projection fields:

- `title`;
- `currency`;
- `estimate_min`;
- `estimate_max`;
- `published_at`.

It can never return:

- organization, calculation, version or creator identifiers;
- input/ruleset/output snapshots or their digests;
- acquisition/material/operating costs;
- profit or margin internals;
- raw publication share tokens.

### CORS response

A successful widget response returns:

- `Access-Control-Allow-Origin` equal to the exact validated origin;
- `Vary: Origin`;
- `Cache-Control: no-store`.

Wildcard `Access-Control-Allow-Origin: *` is forbidden for this boundary.

When an allowed origin reaches its quota, the 429 response also carries the same exact CORS origin and `Vary: Origin`, allowing browser code to observe the real quota response without broadening access.

### Tenant administration

Only authenticated `owner` and `admin` members may:

- create a deployment;
- add/remove allowed origins;
- disable a deployment.

All tenant-owned widget relations use composite tenant foreign keys where applicable so an application filtering bug cannot bind a deployment or origin to another organization's resources.

Deployment disable is idempotent and audited. Origin changes are audited. Origin registry mutations lock the deployment row so concurrent add/remove/disable administration shares one serialization point; add also enforces the maximum registry size while holding that lock.

### Atomic usage quota

Each deployment has a configured hourly request limit. Usage is stored in UTC-hour buckets.

Quota reservation uses one PostgreSQL `INSERT ... ON CONFLICT DO UPDATE ... WHERE ... RETURNING` statement. The update occurs only while the existing count is below the deployment limit. If no row is returned, the request fails with HTTP 429.

This makes the limit authoritative under concurrent API workers without a read-then-write race.

Rate-limit responses expose:

- `X-RateLimit-Limit`;
- `X-RateLimit-Remaining`;
- `X-RateLimit-Reset`;
- `Retry-After` on 429.

## Consequences

- A copied deployment UUID alone does not expose internal business data.
- Forging `Origin` outside a browser can at most retrieve the same customer-safe projection intended for publication.
- Widget embed access can be revoked either by disabling the deployment, removing an origin, or revoking its source public projection.
- Usage accounting has a PostgreSQL write cost per successful widget request; this is accepted for the first authoritative implementation.
- Exact-origin policy means each scheme/host/port variant must be registered explicitly.
- Internationalized origins retain browser-compatible domain identity instead of collapsing to legacy IDNA 2003 mappings.

## Deferred

- CDN-facing public hostname and routing aliases.
- Widget JavaScript SDK and framework wrappers.
- Redis-backed burst limits or finer-than-hour windows.
- Subscription-plan quota aggregation across deployments.
- API keys/OAuth for server-to-server integrations.
- Domain-ownership verification ceremonies.
- White-label custom domains.
- Lead, quote, CRM and webhook integrations.
