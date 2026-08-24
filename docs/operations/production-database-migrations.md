# Production Database Migration Ceremony

Production schema changes are an explicit deployment step. The API process never runs Alembic migrations during application startup.

## Preconditions

- `DATABASE_URL` is supplied at runtime and passes the canonical `postgresql+psycopg` validation.
- The repository contains exactly one Alembic head.
- The target PostgreSQL database is reachable.
- The database does not report multiple Alembic heads.
- No other deployment actor holds the Maliyet Platformu migration advisory lock.

## Command

Run from `services/api` with the production runtime environment loaded:

```bash
python scripts/production_migrate.py
```

The command performs, in order:

1. runtime database URL validation without printing credentials;
2. PostgreSQL readiness check;
3. a session-level PostgreSQL advisory lock acquisition;
4. repository/database Alembic-head validation;
5. `alembic upgrade head`;
6. post-upgrade verification that the database reached the exact repository head;
7. advisory lock release.

Any failed precondition aborts the ceremony. A concurrent migration actor is rejected rather than allowed to race.

## Deployment ordering

Use the following production order:

1. provision database and secrets;
2. run the migration ceremony once;
3. start or roll the API workload;
4. verify `/health` liveness and application-level authenticated smoke checks;
5. deploy the web workload.

`/health` remains a process-liveness endpoint and does not claim database readiness. Deployment automation must treat successful migration as a separate prerequisite.

## Rollback boundary

The ceremony does not automatically run Alembic downgrade. Schema rollback is an explicit operator decision because application/data compatibility must be reviewed per release. Failed forward migrations must remain visible and must not be hidden by an automatic downgrade attempt.
