"""Fail closed when the canonical first-release product surface regresses."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require_file(path: str) -> str:
    candidate = ROOT / path
    if not candidate.is_file():
        raise SystemExit(f"First-release scope is missing required file: {path}")
    return candidate.read_text(encoding="utf-8")


def require_fragment(path: str, fragment: str) -> None:
    text = require_file(path)
    if fragment not in text:
        raise SystemExit(f"First-release scope is missing {fragment!r} in {path}")


def main() -> None:
    registry = "services/api/app/engine_registry.py"
    for engine_key in (
        "food_manufacturing",
        "textile_manufacturing",
        "basic_metals",
        "ecommerce",
        "trade",
        "transportation",
        "accommodation",
        "tourism",
        "target_profit_pricing",
        "asset_depreciation",
        "tax_reconciliation",
        "personnel_cost",
    ):
        require_fragment(registry, f'"{engine_key}": RegisteredEngine(')

    for path in (
        "apps/web/package.json",
        "services/api/app/report_export_api.py",
        "services/api/app/report_export.py",
        "services/api/app/report_export_pdf.py",
        "services/api/app/partner_api_public_api.py",
        "integrations/wordpress/maliyet-platformu-widget.php",
        "compose.production.yml",
        ".github/workflows/release.yml",
        "services/api/scripts/production_migrate.py",
        "services/api/scripts/production_baseline.py",
        "services/api/app/production_readiness.py",
        "data/tr/2026/baseline.json",
    ):
        require_file(path)

    report_api = "services/api/app/report_export_api.py"
    for extension in ("csv", "xlsx", "docx", "pdf"):
        require_fragment(report_api, f"report.{extension}")

    require_fragment("services/api/app/organization_api.py", "router.include_router(report_export_router)")
    require_fragment("services/api/app/organization_api.py", "router.include_router(partner_api_public_router)")
    require_fragment("services/api/app/organization_api.py", "router.include_router(widget_public_router)")

    release = ".github/workflows/release.yml"
    for fragment in (
        "provenance: mode=max",
        "sbom: true",
        "actions/attest-build-provenance@v2",
        "release-manifest.json",
    ):
        require_fragment(release, fragment)

    rollout = "compose.production.yml"
    for service in ("migrate", "baseline", "readiness", "api", "web"):
        require_fragment(rollout, f"  {service}:\n")

    require_fragment("README.md", "Kanonik ilk sürüm kapsamı: **TAMAM**")
    print("Canonical first-release scope: PASS")


if __name__ == "__main__":
    main()
