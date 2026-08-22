"""Regression tests for browser-compatible widget origin canonicalization."""

from app.widget_security import normalize_https_origin


def test_idn_uses_nontransitional_uts46_and_keeps_distinct_ascii_domain() -> None:
    """Sharp-s IDN must canonicalize to its browser A-label, not legacy `ss`."""

    internationalized = normalize_https_origin("https://faß.de")
    ascii_domain = normalize_https_origin("https://fass.de")

    assert internationalized == "https://xn--fa-hia.de"
    assert ascii_domain == "https://fass.de"
    assert internationalized != ascii_domain


def test_uts46_normalizes_case_before_exact_origin_matching() -> None:
    assert normalize_https_origin("https://König.Example/") == "https://xn--knig-5qa.example"
