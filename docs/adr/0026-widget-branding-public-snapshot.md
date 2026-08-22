# ADR 0026 — Tenant Widget Branding Profiles and Immutable Public Presentation Snapshots

- **Status:** Accepted
- **Date:** 2026-08-22
- **Scope:** Widget presentation configuration only

## Context

Widget SDK v1.1 introduced a strict browser-side presentation surface (`theme`, `locale`,
`density`, `showTitle` and documented CSS variables), while deliberately keeping formulas,
legislation data, credentials and private calculation state on the server.

A tenant now needs to prepare and reuse branding settings without allowing an edit to a draft
profile to silently mutate an already-published customer experience. The public widget boundary
must also remain customer-safe and backward compatible with already-published SDK assets.

## Decision

### Mutable tenant draft

`widget_branding_profiles` stores a tenant-owned mutable draft. Only authenticated `owner` and
`admin` actors can create, read, list or update these profiles.

The accepted surface is deliberately bounded:

- `theme`: `auto | light | dark`
- `locale`: `tr | en`
- `density`: `comfortable | compact`
- `show_title`: boolean
- seven canonical `#RRGGBB` color tokens
- `border_radius_px`: integer `0..32`
- `font_family`: `system | sans | serif | monospace`

Arbitrary HTML, CSS, JavaScript, font URLs, image URLs and custom class names are not accepted.
The profile contains no financial rule, tax rate, threshold, API key, token or tenant secret.

Each update advances a monotonic profile revision and records the authenticated updater.

### Immutable publication snapshot

Publishing never exposes the mutable profile directly. The server row-locks the active deployment
and selected same-tenant profile, copies the complete allowlisted presentation into a new
`widget_presentation_snapshots` row, and then atomically points that deployment at the new snapshot
through `widget_published_presentations`.

Changing a profile after publication therefore has no public effect until a new explicit publish
operation creates another immutable snapshot.

Composite tenant foreign keys prevent a deployment from pointing at another organization's
presentation snapshot. Publication actions are audit logged.

### Public response

The existing exact-Origin and atomic-quota protected projection endpoint may include a nested
`presentation` object sourced only from the currently published immutable snapshot. It contains no
organization, deployment, profile or snapshot identifiers.

For deployments without a published presentation the field is omitted, preserving the existing
v1 public JSON shape. Existing immutable SDK v1.0.0 and v1.1.0 assets are not modified; they ignore
the additive presentation field. A later SDK version may consume this server-published object.

No second public HTTP request is introduced, so one widget mount still reserves exactly one quota
unit.

## Tenant and security consequences

- Profile management and publication require authenticated owner/admin membership.
- Profile and snapshot ownership is encoded with composite database foreign keys.
- Public output remains an explicit allowlist and never includes internal calculation snapshots,
  costs, profits, margins, rulesets, raw share tokens or branding persistence identifiers.
- Origin authorization remains exact HTTPS DNS-origin matching; `Referer` is not used.
- Quota authority remains the existing PostgreSQL atomic reservation path.
- Published SDK version paths remain byte-immutable.

## Migration

Alembic revision `0008_widget_branding_profiles` creates:

1. `widget_branding_profiles`
2. `widget_presentation_snapshots`
3. `widget_published_presentations`

The migration is reversible and remains a single-head continuation of
`0007_widget_domain_security`.

## Out of scope

- Logo or media upload
- Arbitrary CSS or custom fonts
- White-label/custom domains
- Billing or plan entitlements
- Changing tax/SGK/KDV rules or financial formulas
- Modifying published SDK v1.0.0 or v1.1.0 assets
- Automatic browser application of server-published branding; that belongs to a new semver SDK PR
