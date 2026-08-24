# Production readiness contract

Production traffic must not be routed to the API merely because the process responds to `/health`.

The deployment order is:

1. Build the immutable API artifact.
2. Provide the production `DATABASE_URL` at runtime.
3. Run the explicit production migration ceremony from the production API artifact.
4. Run `python -m app.production_readiness` from that same artifact.
5. Route traffic only after the readiness command exits successfully.

The readiness command is deliberately read-only. It verifies:

- the runtime URL is the canonical `postgresql+psycopg` URL;
- PostgreSQL is reachable with `SELECT 1`;
- the repository has exactly one Alembic head;
- the database reports exactly one Alembic head;
- the database head exactly matches the repository head.

It never upgrades, stamps, repairs, or guesses migration state. Missing, multiple, stale, or future heads fail closed. Error messages must not echo credentials from `DATABASE_URL`.

`/health` remains a dependency-free liveness signal suitable for process restart decisions. The production readiness command is the gate for admitting traffic after migration and before rollout completion.
