# ADR 0027 — Widget SDK v1.2 Server-Published Branding Consumption

- **Status:** Accepted
- **Date:** 2026-08-22
- **Scope:** Browser presentation consumption only

## Context

ADR 0026 introduced tenant-owned mutable branding drafts and immutable presentation snapshots. The public projection endpoint may now include an allowlisted `presentation` object, but the published Widget SDK v1.0.0 and v1.1.0 assets are immutable and intentionally ignore it.

A new SDK version is required to consume that presentation without moving financial authority, private tenant state, secrets or executable styling into the browser.

## Decision

Widget SDK v1.2.0 consumes the additive server `presentation` object from the same exact-Origin, atomic-quota protected projection GET already used for estimate data. It does not issue a second request.

The SDK validates every consumed server field before rendering:

- `theme`: `auto | light | dark`
- `locale`: `tr | en`
- `density`: `comfortable | compact`
- `show_title`: boolean
- seven uppercase `#RRGGBB` color tokens
- `border_radius_px`: integer `0..32`
- `font_family`: `system | sans | serif | monospace`

Malformed or partially malformed published presentation data makes the complete widget response fail closed as `invalid_response`. An absent `presentation` field is valid and preserves the legacy SDK-default behavior.

## Precedence contract

Resolved display options use this order:

1. explicit programmatic mount option
2. HTML dataset option
3. server-published immutable presentation snapshot
4. SDK default

This preserves v1.1 per-embed compatibility. Published color, radius and font tokens have no programmatic/dataset equivalent and are applied when the server presentation is present.

## Safe CSS mapping

Server values never become selectors, property names, HTML, JavaScript, URLs or stylesheet source. The loader maps validated values only to a fixed set of CSS custom property names through `CSSStyleDeclaration.setProperty` and maps font tokens through fixed SDK-owned font stacks.

The SDK does not create `<style>` elements, does not call `setAttribute("style", ...)`, does not use `innerHTML`, `eval` or `Function`, and does not accept `url(...)` or `@import` input.

## Financial and security boundary

- `estimate_min` / `estimate_max` remain decimal strings and are displayed without `Number`, `parseFloat` or `Intl.NumberFormat` financial conversion.
- Browser requests remain simple credential-free CORS GET with `credentials: "omit"` and `referrerPolicy: "no-referrer"`.
- No Authorization header, API key, bearer token or tenant secret is introduced.
- Extra/private response fields are never rendered.
- Origin authorization and quota authority remain server-side.

## Immutability

Published v1.0.0 and v1.1.0 assets remain byte-for-byte unchanged. CI locks the v1.0.0 SHA-256 and the canonical Git blob identities for the v1.1.0 loader and stylesheet while testing v1.2.0 separately.

## CSP

v1.2.0 requires only the existing external SDK stylesheet/script and API connection origins. It does not generate executable HTML or stylesheet source and does not require `unsafe-eval`. No `<style>` tag or style-attribute injection is used.

## Consequences

A tenant may update a mutable branding profile without changing a live embed. Only explicit publication changes the server snapshot seen by v1.2.0. Older v1.0.0/v1.1.0 embeds continue to behave exactly as before.
