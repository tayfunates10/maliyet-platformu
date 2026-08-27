# Production readiness contract

Production traffic must not be routed to the API merely because the process responds to `/health`.

The deployment order is:

1. Build the immutable API artifact.
2. Provide the production `DATABASE_URL` at runtime.
3. Run the explicit production migration ceremony from the production API artifact.
4. Run the explicit TR-2026 regulatory baseline ceremony from that same artifact.
5. Run `python -m app.production_readiness` from that same artifact.
6. Route traffic only after the readiness command exits successfully.

The readiness command is deliberately read-only. It verifies:

- the runtime URL is the canonical `postgresql+psycopg` URL;
- PostgreSQL is reachable with `SELECT 1`;
- the repository has exactly one Alembic head;
- the database reports exactly one Alembic head;
- the database head exactly matches the repository head;
- the packaged TR-2026 baseline manifest and every captured official-source evidence file pass SHA-256 verification;
- every persisted baseline source, definition and revision exactly matches that reviewed manifest.

It never upgrades, stamps, repairs, seeds or guesses migration/rule state. Missing, multiple, stale or future Alembic heads fail closed. Missing or drifted regulatory baseline material also fails closed. Error messages must not echo credentials from `DATABASE_URL`.

The baseline ceremony is separate from migrations and application startup. It is idempotent, PostgreSQL-advisory-lock serialized and transactional. It must be run after schema migration and before readiness. Hash mismatch or persisted rule drift aborts the ceremony rather than silently replacing evidence.

`/health` remains a dependency-free liveness signal suitable for process restart decisions. The production readiness command is the gate for admitting traffic after migration and baseline loading and before rollout completion.
