# ADR 0019: Local password authentication and current-session revocation

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

ADR 0017 established high-entropy opaque bearer sessions but intentionally left session issuance as an internal primitive. The product now needs a local registration/login path without weakening the existing server-side session boundary.

Password authentication is security-sensitive and must not introduce plaintext storage, fast general-purpose hashes, reversible encryption, caller-selected session identity, or lockout state that silently disappears because an HTTP 401 rolls back the request transaction.

## Decision

### Credential isolation

Local password material is stored in a separate `user_credentials` table keyed one-to-one by `users.id`. A `User` may therefore exist without a local password credential, which preserves a clean path for future SSO/OIDC identities.

The credential row stores only:

- versioned password hash string;
- failed-attempt count;
- temporary `locked_until` timestamp;
- password-change and creation timestamps.

Raw passwords are never persisted or logged by the application.

### Password hashing

Local credentials use Python's built-in memory-hard `hashlib.scrypt` with a per-password cryptographically random salt. The encoded hash records its algorithm version and work parameters so future upgrades can be explicit and testable.

Current parameters:

- `N = 2^15`
- `r = 8`
- `p = 3`
- derived-key length `64` bytes
- random salt `16` bytes

These parameters follow an OWASP-accepted scrypt profile while avoiding a new native authentication dependency in this stage.

References:

- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- Python `hashlib.scrypt`: https://docs.python.org/3/library/hashlib.html#hashlib.scrypt

Passwords use a length policy rather than composition rules. Registration accepts 12–256 characters and preserves password whitespace exactly as entered.

### Enumeration and brute-force resistance

Login returns the same generic `invalid credentials` response for unknown users, invalid passwords and temporarily locked accounts. Unknown users execute a fixed dummy scrypt verification path to reduce obvious user-enumeration timing differences.

A credential is temporarily locked after five failed attempts for 15 minutes. The credential row is selected `FOR UPDATE` so concurrent failed attempts serialize at the account boundary.

Failed-login state is security state. The HTTP login handler returns a normal 401 `Response` instead of throwing after the mutation, allowing the request transaction dependency to commit the failed-attempt/lockout update.

Broader IP/device/network rate limiting remains a separate gateway/Redis responsibility and is not replaced by account lockout.

### Registration and session issuance

`POST /auth/register`:

1. normalizes the email identifier;
2. validates password policy;
3. creates the `User` and `UserCredential` atomically;
4. relies on the database unique email constraint as the final duplicate-registration barrier;
5. issues the existing opaque bearer session.

`POST /auth/login` authenticates the password and then calls the same `issue_session` primitive. Raw bearer tokens are returned only at issuance; the database retains only their SHA-256 digests.

Token responses set `Cache-Control: no-store`.

### Current-session identity and logout

`AuthenticatedIdentity` now carries both `user_id` and the authenticated `auth_session_id`. The latter is derived only from the bearer-token lookup; callers cannot submit it.

`POST /auth/logout` revokes exactly that current session. Other independently issued sessions for the same user remain valid.

`GET /auth/me` returns the active authenticated user's non-secret profile.

## Security consequences

- No plaintext or reversible password storage.
- No SHA/MD5/general fast digest used as a password KDF.
- Per-password random salts prevent identical hashes for identical passwords.
- Hash format is explicitly versioned.
- Unknown-user login takes the memory-hard verification path.
- Account lockout state cannot disappear merely because the endpoint returns HTTP 401.
- Logout revokes only the server-resolved current session.
- Existing opaque bearer token digest storage remains unchanged.

## Migration consequences

Migration `0005_user_credentials` creates the credential table and remains inside the Alembic `VARCHAR(32)` revision-id contract. Alembic runtime metadata explicitly imports auxiliary auth/rules models so standalone migration drift checks see the complete schema.

## Deferred

- Email verification.
- Password reset/recovery ceremony.
- MFA/WebAuthn/TOTP.
- Password hash parameter rehash-on-login migration.
- IP/device adaptive rate limiting and abuse detection.
- SSO/OIDC providers.
- Organization/business onboarding after identity creation.
