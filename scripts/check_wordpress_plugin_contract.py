"""Fail fast when the WordPress widget integration weakens public-widget boundaries."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "integrations" / "wordpress" / "maliyet-platformu-widget.php"


def require(text: str, fragment: str) -> None:
    if fragment not in text:
        raise SystemExit(f"WordPress widget contract is missing: {fragment}")


def forbid(text: str, fragment: str) -> None:
    if fragment in text:
        raise SystemExit(f"WordPress widget contract contains forbidden text: {fragment}")


def main() -> None:
    text = PLUGIN.read_text(encoding="utf-8")

    for fragment in (
        "Plugin Name: Maliyet Platformu Widget",
        "const MALIYET_WIDGET_VERSION = '1.2.0';",
        "wp_parse_url",
        "($parts['scheme'] ?? '') !== 'https'",
        "esc_attr($deployment_id)",
        "esc_url($stylesheet)",
        "esc_url($loader)",
        "esc_attr($api_base)",
        "data-maliyet-widget",
        "data-deployment-id",
        "data-maliyet-api-base",
        "/widget/' . MALIYET_WIDGET_VERSION . '/loader.js",
        "/widget/' . MALIYET_WIDGET_VERSION . '/styles.css",
        "add_shortcode('maliyet_widget', 'maliyet_widget_shortcode')",
    ):
        require(text, fragment)

    for forbidden in (
        "Authorization",
        "api_key",
        "client_secret",
        "bearer",
        "wp_remote_get",
        "wp_remote_post",
        "eval(",
        "base64_decode",
        "innerHTML",
    ):
        forbid(text, forbidden)

    print("WordPress widget contract: PASS")


if __name__ == "__main__":
    main()
