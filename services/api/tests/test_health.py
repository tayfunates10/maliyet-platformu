"""Tests for the dependency-free API health contract."""

from app.main import SERVICE_NAME, SERVICE_VERSION, health


def test_health_contract_is_stable() -> None:
    response = health()

    assert response.status == "ok"
    assert response.service == SERVICE_NAME
    assert response.version == SERVICE_VERSION
