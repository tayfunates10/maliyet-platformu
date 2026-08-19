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
    "docs/adr/0002-tenant-data-model.md",
    "docs/adr/0003-rules-engine-foundation.md",
    "docs/adr/0004-tr-2026-baseline-provenance.md",
    "docs/adr/0005-decimal-calculation-kernel.md",
    "docs/adr/0006-core-costing-engine.md",
    "docs/adr/0007-manufacturing-core.md",
    "docs/adr/0008-food-manufacturing-adapter.md",
    "docs/adr/0009-textile-manufacturing-adapter.md",
    "docs/adr/0010-basic-metals-manufacturing-adapter.md",
    "docs/adr/0011-commerce-ecommerce-core.md",
    "docs/adr/0012-transportation-costing.md",
    "docs/adr/0013-accommodation-costing.md",
    "docs/adr/0014-tourism-package-costing.md",
    "docs/data-sources/turkiye-authoritative-sources.md",
    "docs/engineering/pr-quality-gates.md",
    ".github/pull_request_template.md",
    "data/tr/2026/README.md",
    "data/tr/2026/baseline.json",
    "data/tr/2026/source_captures/gib_income_tax_tariff_2026.json",
    "data/tr/2026/source_captures/gib_provisional_tax_rates_2026.json",
    "data/tr/2026/source_captures/gib_corporate_tax_2026.json",
    "data/tr/2026/source_captures/gib_vat_rates_2026.json",
    "data/tr/2026/source_captures/sgk_4a_pek_2026.json",
    "data/tr/2026/source_captures/sgk_4a_premium_rates_2026.json",
    "services/api/pyproject.toml",
    "services/api/alembic.ini",
    "services/api/alembic/env.py",
    "services/api/alembic/versions/0001_tenant_core.py",
    "services/api/alembic/versions/0002_rules_engine_foundation.py",
    "services/api/app/main.py",
    "services/api/app/models.py",
    "services/api/app/tenancy.py",
    "services/api/app/rules_models.py",
    "services/api/app/rules_engine.py",
    "services/api/app/baseline_loader.py",
    "services/api/app/calculation_kernel.py",
    "services/api/app/costing_engine.py",
    "services/api/app/manufacturing_engine.py",
    "services/api/app/food_manufacturing.py",
    "services/api/app/textile_manufacturing.py",
    "services/api/app/basic_metals_manufacturing.py",
    "services/api/app/commerce_engine.py",
    "services/api/app/transportation_engine.py",
    "services/api/app/accommodation_engine.py",
    "services/api/app/tourism_engine.py",
    "services/api/tests/test_health.py",
    "services/api/tests/test_migrations.py",
    "services/api/tests/test_tenant_isolation.py",
    "services/api/tests/test_rules_engine.py",
    "services/api/tests/test_tr_2026_baseline.py",
    "services/api/tests/test_calculation_kernel.py",
    "services/api/tests/test_costing_engine.py",
    "services/api/tests/test_manufacturing_engine.py",
    "services/api/tests/test_food_manufacturing.py",
    "services/api/tests/test_textile_manufacturing.py",
    "services/api/tests/test_basic_metals_manufacturing.py",
    "services/api/tests/test_commerce_engine.py",
    "services/api/tests/test_transportation_engine.py",
    "services/api/tests/test_accommodation_engine.py",
    "services/api/tests/test_tourism_engine.py",
    "apps/web/package.json",
    "apps/web/app/page.tsx",
    "apps/web/scripts/check-contract.mjs",
)

AGENT_GUARDRAILS = (
    "Mevzuat oranı ve parasal eşik kod içine hard-code edilmez.",
    "Para hesapları binary `float` ile yapılmaz.",
    "Tenant izolasyonu güvenlik sınırıdır",
    "CI kırmızıysa iş tamamlandı olarak raporlanmaz.",
    "Her yeni PR güncel `main` dalından açılır.",
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
