"""Run the explicit production regulatory baseline ceremony."""

from __future__ import annotations

from app.http_dependencies import get_database_url
from app.production_baseline import run_production_baseline_ceremony


def main() -> None:
    result = run_production_baseline_ceremony(get_database_url())
    print(
        "Production regulatory baseline: PASS "
        f"({result.sources} sources, {result.definitions} definitions, {result.versions} versions)"
    )


if __name__ == "__main__":
    main()
