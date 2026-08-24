# Production rollout contract

Production rollout must preserve the same fail-closed boundaries used by CI and the API runtime. `compose.production.yml` is the canonical single-host/container-orchestrator contract for the first production release; it is not a development compose file.

## Required runtime inputs

- `API_IMAGE_REPOSITORY` + `API_IMAGE_DIGEST`: API registry repository and exact sha256 digest. The repository value must not contain a mutable tag or embedded digest; the digest must be exactly 64 lowercase hexadecimal characters.
- `WEB_IMAGE_REPOSITORY` + `WEB_IMAGE_DIGEST`: web registry repository and exact sha256 digest under the same validation contract.
- `DATABASE_URL`: canonical `postgresql+psycopg` production database URL supplied by the secret/runtime environment. It must never be committed to this repository.
- `API_BASE_URL`: externally valid HTTPS API origin consumed by the server-side web management proxy.
- Optional `API_PORT` / `WEB_PORT`: loopback host ports. Public TLS termination/reverse proxying stays outside the application containers.

Before any deployment command, run `python scripts/check_production_rollout_contract.py` in the same environment that provides the image repository/digest values. This validates the actual runtime image inputs, not only the Compose template.

## Canonical rollout order

1. Run migration as a separate explicit ceremony: `docker compose -f compose.production.yml --profile migration run --rm migrate`. The migration service is profile-gated and is deliberately absent from normal application startup.
2. After migration succeeds, start the application with `docker compose -f compose.production.yml up -d api web`. Compose runs the read-only `readiness` dependency from the same API digest; readiness requires database head == repository head before API can start.
3. `web` starts only after the API container is healthy. External traffic must remain closed until the operator/reverse proxy has verified the application endpoints.

If migration or readiness fails, the rollout stops. Never bypass the explicit migration ceremony, and never start API/web against an unverified database.

## Security boundaries

The compose contract does not build images in production, does not embed database credentials, does not run a bundled PostgreSQL server, and binds application ports to loopback by default. API and web filesystems are read-only except for bounded tmpfs mounts. Database backup/restore, TLS termination, registry authentication and host firewall configuration remain infrastructure responsibilities and must not weaken tenant, Decimal, rules-engine or widget controls.

## Rollback

Application rollback without a database restoration is allowed only when the target release has the **exact same Alembic repository head** as the database. The readiness gate intentionally rejects an older image whose repository head differs, even if a migration is believed to be backward-compatible.

Never run an Alembic downgrade automatically during rollback. If the target release has a different Alembic head, recovery requires an explicit reviewed database restoration or forward-fix migration plan before switching image digests. After that plan establishes database head == target repository head, run readiness again before starting API/web.
