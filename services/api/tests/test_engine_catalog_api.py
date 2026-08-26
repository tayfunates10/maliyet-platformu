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
        "personnel_cost",
    }
    assert all(item["execution_requires_trusted_actor"] is True for item in payload)
    regulatory = {item["key"] for item in payload if item["regulatory_rules_applied"] is True}
    assert regulatory == {"personnel_cost"}


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


def test_personnel_cost_detail_requires_server_resolved_rules() -> None:
    response = client.get("/engines/personnel_cost")

    assert response.status_code == 200
    payload = response.json()
    assert payload["engine_version"] == "personnel-cost-v1"
    assert payload["regulatory_rules_applied"] is True
    assert payload["input_schema"]["additionalProperties"] is False
    properties = payload["input_schema"]["properties"]
    assert properties["at_date"]["type"] == "string"
    assert properties["gross_cash_compensation"]["type"] == "string"
    assert properties["declared_monthly_earnings"]["type"] == "string"
    line_schema = payload["input_schema"]["$defs"]["EmployerCostLineInput"]
    assert line_schema["additionalProperties"] is False
    assert line_schema["properties"]["amount"]["type"] == "string"
    assert "employer_sgk_rate" not in properties


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
