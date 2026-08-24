# Production rollout contract

Production rollout must preserve the same fail-closed boundaries used by CI and the API runtime. `compose.production.yml` is the canonical single-host/container-orchestrator contract for the first production release; it is not a development compose file.

## Required runtime inputs

- `API_IMAGE`: immutable API image reference. Prefer a registry digest such as `registry.example/api@sha256:...`; mutable `latest` tags are forbidden by repository contract.
- `WEB_IMAGE`: immutable web image reference, likewise pinned to an immutable release artifact.
- `DATABASE_URL`: canonical `postgresql+psycopg` production database URL supplied by the secret/runtime environment. It must never be committed to this repository.
- `API_BASE_URL`: externally valid HTTPS API origin consumed by the server-side web management proxy.
- Optional `API_PORT` / `WEB_PORT`: loopback host ports. Public TLS termination/reverse proxying stays outside the application containers.

## Canonical rollout order

1. Run `migrate` exactly once with the release API image. The existing production migration ceremony obtains the PostgreSQL advisory lock and upgrades to the single repository Alembic head.
2. Run `readiness` from the same API image. It is read-only and requires database head == repository head.
3. Start `api` only after readiness completed successfully.
4. Start `web` only after the API service has started. External traffic must still remain closed until the operator/reverse proxy has verified the application endpoints.

If migration or readiness fails, the rollout stops. Do not bypass either service by starting API/web manually against an unverified database.

## Security boundaries

The compose contract does not build images in production, does not embed database credentials, does not run a bundled PostgreSQL server, and binds application ports to loopback by default. API and web filesystems are read-only except for bounded tmpfs mounts. Database backup/restore, TLS termination, registry authentication and host firewall configuration remain infrastructure responsibilities and must not weaken tenant, Decimal, rules-engine or widget controls.

## Rollback

Application rollback is safe only when the target older release is schema-compatible with the already-applied database head. Never run an Alembic downgrade automatically during rollback. If a release migration is not backward compatible, recovery requires an explicit reviewed database restoration/migration plan before switching image digests.
