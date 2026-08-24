"""Run the explicit production database migration ceremony."""

from __future__ import annotations

from app.http_dependencies import get_database_url
from app.production_migrations import run_production_migration_ceremony


def main() -> None:
    target_head = run_production_migration_ceremony(get_database_url())
    print(f"Production database migration: PASS ({target_head})")


if __name__ == "__main__":
    main()
