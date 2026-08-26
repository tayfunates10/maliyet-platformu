"""HTTP tests for the non-executable engine catalog."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_engine_catalog_lists_all_allowlisted_engines() -> None:
    response = client.get("/engines")

    assert response.status_code == 200
    payload = response.json()
    assert {item["key"] for item in payload} == {
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
    }
    assert all(item["execution_requires_trusted_actor"] is True for item in payload)
    assert all(item["regulatory_rules_applied"] is False for item in payload)


def test_engine_detail_returns_strict_input_schema() -> None:
    response = client.get("/engines/trade")

    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == "trade"
    assert payload["input_schema"]["type"] == "object"
    assert payload["input_schema"]["additionalProperties"] is False


def test_target_profit_detail_requires_decimal_strings() -> None:
    response = client.get("/engines/target_profit_pricing")

    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == "target_profit_pricing"
    assert payload["engine_version"] == "target-profit-pricing-v2"
    assert payload["input_schema"]["additionalProperties"] is False
    properties = payload["input_schema"]["properties"]
    assert properties["variable_cost_per_unit"]["type"] == "string"
    assert properties["fixed_costs"]["type"] == "string"
    assert properties["target_profit"]["type"] == "string"
    assert properties["expected_units"]["type"] == "string"


def test_asset_depreciation_detail_keeps_money_as_strings() -> None:
    response = client.get("/engines/asset_depreciation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == "asset_depreciation"
    assert payload["engine_version"] == "asset-depreciation-v1"
    assert payload["input_schema"]["additionalProperties"] is False
    properties = payload["input_schema"]["properties"]
    assert properties["acquisition_cost"]["type"] == "string"
    assert properties["residual_value"]["type"] == "string"
    assert properties["useful_life_months"]["type"] == "integer"
    assert properties["elapsed_months"]["type"] == "integer"


def test_tax_reconciliation_detail_keeps_money_as_strings() -> None:
    response = client.get("/engines/tax_reconciliation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == "tax_reconciliation"
    assert payload["engine_version"] == "tax-reconciliation-v1"
    assert payload["input_schema"]["additionalProperties"] is False
    properties = payload["input_schema"]["properties"]
    assert properties["accounting_profit_before_tax"]["type"] == "string"
    adjustment_schema = payload["input_schema"]["$defs"]["TaxBaseAdjustmentInput"]
    assert adjustment_schema["additionalProperties"] is False
    assert adjustment_schema["properties"]["amount"]["type"] == "string"


def test_unknown_engine_returns_404() -> None:
    response = client.get("/engines/not-real")

    assert response.status_code == 404
    assert response.json() == {"detail": "engine not found"}


def test_public_execution_endpoint_is_not_exposed_before_auth() -> None:
    response = client.post(
        "/engines/trade/execute",
        json={
            "sales": [
                {
                    "key": "sale",
                    "quantity": "1",
                    "unit_sale_price": "100.00",
                    "unit_acquisition_cost": "40.00",
                }
            ]
        },
    )

    assert response.status_code == 404
