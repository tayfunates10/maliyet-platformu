"""Fail fast when the production rollout contract becomes unsafe."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.production.yml"


def require(text: str, fragment: str) -> None:
    if fragment not in text:
        raise SystemExit(f"Production rollout contract is missing: {fragment}")


def forbid(text: str, fragment: str) -> None:
    if fragment in text:
        raise SystemExit(f"Production rollout contract contains forbidden text: {fragment}")


def main() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    for service in ("migrate", "readiness", "api", "web"):
        require(text, f"  {service}:\n")

    require(text, "${API_IMAGE_REPOSITORY:?API_IMAGE_REPOSITORY is required}@sha256:")
    require(text, "${API_IMAGE_DIGEST:?API_IMAGE_DIGEST is required}")
    require(text, "${WEB_IMAGE_REPOSITORY:?WEB_IMAGE_REPOSITORY is required}@sha256:")
    require(text, "${WEB_IMAGE_DIGEST:?WEB_IMAGE_DIGEST is required}")
    require(text, "${DATABASE_URL:?DATABASE_URL is required}")
    require(text, "${API_BASE_URL:?API_BASE_URL is required}")
    require(text, 'command: ["python", "scripts/production_migrate.py"]')
    require(text, 'command: ["python", "-m", "app.production_readiness"]')
    require(text, "condition: service_completed_successfully")
    require(text, "condition: service_healthy")
    require(text, 'restart: "no"')
    require(text, "read_only: true")
    require(text, '"127.0.0.1:${API_PORT:-8000}:8000"')
    require(text, '"127.0.0.1:${WEB_PORT:-3000}:3000"')

    for forbidden in (
        ":latest",
        "postgresql+psycopg://",
        "password:",
        "POSTGRES_PASSWORD",
        "build:",
    ):
        forbid(text, forbidden)

    migrate_index = text.index("  migrate:\n")
    readiness_index = text.index("  readiness:\n")
    api_index = text.index("  api:\n")
    web_index = text.index("  web:\n")
    if not migrate_index < readiness_index < api_index < web_index:
        raise SystemExit("Production rollout services are not in canonical rollout order")

    print("Production rollout contract: PASS")


if __name__ == "__main__":
    main()
