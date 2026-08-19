"""Fail fast when repository-wide architecture/handoff contracts disappear."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "README.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "docs/product-scope.md",
    "docs/adr/0001-system-architecture.md",
    "docs/engineering/pr-quality-gates.md",
    ".github/pull_request_template.md",
    "services/api/pyproject.toml",
    "services/api/app/main.py",
    "services/api/tests/test_health.py",
)

AGENT_GUARDRAILS = (
    "Mevzuat oranı ve parasal eşik kod içine hard-code edilmez.",
    "Para hesapları binary `float` ile yapılmaz.",
    "Tenant izolasyonu güvenlik sınırıdır",
    "CI kırmızıysa iş tamamlandı olarak raporlanmaz.",
)


def main() -> None:
    missing = [relative for relative in REQUIRED_FILES if not (ROOT / relative).is_file()]
    if missing:
        raise SystemExit(f"Missing repository contract files: {', '.join(missing)}")

    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    missing_guardrails = [text for text in AGENT_GUARDRAILS if text not in agents]
    if missing_guardrails:
        raise SystemExit(
            "AGENTS.md is missing locked guardrails: " + "; ".join(missing_guardrails)
        )

    print("Repository contract: PASS")


if __name__ == "__main__":
    main()
