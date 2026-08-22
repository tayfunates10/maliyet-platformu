# ADR 0028 — Widget Branding Management UI and Explicit Publish Workflow

- **Status:** Accepted
- **Date:** 2026-08-22
- **Scope:** Authenticated tenant branding management UI

## Context

ADR 0026 introduced tenant-owned mutable branding profiles and immutable published snapshots. ADR 0027 added Widget SDK v1.2 consumption of those snapshots. A tenant owner/admin still needs a browser workflow to create and edit drafts and explicitly publish a saved revision to a widget deployment.

The API uses opaque bearer sessions. Persisting those raw bearer tokens in `localStorage`, `sessionStorage`, IndexedDB or cookies from this first management shell would expand the credential attack surface. Direct browser-to-API management calls would also require broadening API CORS because authenticated requests carry the `Authorization` header.

## Decision

### Memory-only browser session

The management page obtains an opaque bearer token through `/auth/login` and holds it only in React component memory. The token is never written to persistent browser storage and is never rendered into the DOM, URL, logs or error messages. Refreshing or leaving the page ends the in-memory management session.

The password field is cleared after every login attempt. Logout explicitly clears token, tenant/profile state and publish confirmation state.

### Same-origin allowlisted management proxy

The browser sends management requests only to `/api/management/...` on the Next.js origin. A server-side route handler forwards only a fixed allowlist of API operations:

- `POST /auth/login`
- `GET /organizations`
- `GET /organizations/{organization_id}/widget-branding-profiles`
- `POST /organizations/{organization_id}/widget-branding-profiles`
- `PUT /organizations/{organization_id}/widget-branding-profiles/{profile_id}`
- `POST /organizations/{organization_id}/widget-deployments/{deployment_id}/presentation`

The proxy is not a generic path forwarder. UUID-bearing routes must match canonical UUID patterns, query strings are rejected, request bodies are bounded, login refuses an `Authorization` header, and authenticated routes require one bounded Bearer header.

The upstream API base must be HTTPS. Plain HTTP is accepted only for loopback development (`localhost`, `127.0.0.1`, `::1`). Credentials, query strings and fragments in the configured upstream base are rejected.

The proxy constructs a fresh outbound header set. Browser cookies, `Origin`, `Referer` and arbitrary request headers are not forwarded. Upstream response headers are also not blindly relayed; only a JSON response body, status and fixed no-store/nosniff headers are returned.

This avoids widening API CORS while keeping server-side API authorization authoritative.

### Draft save and publish are separate operations

Creating or updating a branding profile is always a draft-only action. The save handler never calls the publication endpoint.

Publication requires all of the following:

1. an authenticated owner/admin organization,
2. a selected persisted profile,
3. no unsaved local draft changes,
4. a syntactically valid deployment UUID,
5. an explicit user confirmation checkbox,
6. an explicit publish form submission.

Editing a field immediately clears any prior publish confirmation. A successful save also clears publish confirmation and reports that the live widget has not changed.

## Security consequences

- Tenant authorization remains entirely on the API; the UI filters owner/admin organizations only for usability and does not treat that filter as an authorization boundary.
- Bearer credentials are ephemeral in the browser and never persisted.
- The Next.js proxy is route-allowlisted and cannot be used as an arbitrary authenticated API tunnel.
- Save cannot implicitly publish.
- Unsaved changes cannot be published.
- Raw upstream error bodies are not surfaced by the browser API client; UI messages are mapped from bounded status/error categories.
- No financial input/output snapshots, rulesets, margins, tax rates, formulas or tenant secrets are introduced into the management UI.

## Accessibility and usability

The workflow uses semantic forms, labels, status/alert regions, disabled-state guards and mobile-responsive layouts. Publish is visually separated from draft editing and explicitly described as a live action.

## Out of scope

- Persistent browser authentication / refresh-token architecture
- Deployment discovery/list API and deployment picker
- Logo/media upload
- Arbitrary CSS or custom font URLs
- Billing/plan entitlement management
- Financial calculation editing
- Automatic publish after profile save

## Follow-up

A later PR may add authenticated deployment discovery so the publish form can replace manual deployment UUID entry with a tenant-scoped selector. That must preserve the explicit publish ceremony and API tenant authority.
