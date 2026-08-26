"""Tests for the closed calculation-engine registry."""

import pytest

from app.engine_registry import (
    EngineInputValidationError,
    EngineNotFoundError,
    describe_registered_engine,
    execute_registered_engine,
    list_registered_engines,
)


def _payloads() -> dict[str, dict[str, object]]:
    commerce = {
        "sales": [
            {
                "key": "sale",
                "quantity": "1",
                "unit_sale_price": "100.00",
                "unit_acquisition_cost": "40.00",
            }
        ]
    }
    return {
        "food_manufacturing": {
            "output_unit": "kg",
            "recipe_batches": "1",
            "theoretical_output_per_recipe": "10",
            "package_count": 10,
            "package_content_quantity": "1",
        },
        "textile_manufacturing": {
            "theoretical_piece_count": 10,
            "cutting_reject_count": 0,
            "quality_reject_count": 0,
            "ordered_piece_count": 10,
        },
        "basic_metals": {
            "output_unit": "kg",
            "theoretical_output_quantity": "10",
            "melt_loss_quantity": "0",
            "slag_loss_quantity": "0",
            "quality_reject_quantity": "0",
        },
        "ecommerce": commerce,
        "trade": commerce,
        "transportation": {
            "distance": {"loaded_km": "100", "empty_km": "20"},
            "cargo": {"quantity": "2", "unit": "ton"},
        },
        "accommodation": {
            "capacity": {
                "available_rooms_per_night": 1,
                "nights": 1,
                "occupied_room_nights": 1,
            },
            "channel_sales": [
                {
                    "key": "direct",
                    "room_nights": 1,
                    "gross_room_revenue": "100.00",
                }
            ],
        },
        "tourism": {
            "plan": {"participant_count": 1, "currency": "TRY"},
            "channel_sales": [
                {
                    "key": "direct",
                    "participant_count": 1,
                    "gross_revenue": "100.00",
                }
            ],
        },
        "target_profit_pricing": {
            "variable_cost_per_unit": "40.00",
            "fixed_costs": "1000.00",
            "target_profit": "500.00",
            "expected_units": "100",
        },
        "asset_depreciation": {
            "asset_key": "machine-1",
            "acquisition_cost": "120000.00",
            "residual_value": "12000.00",
            "useful_life_months": 60,
            "elapsed_months": 12,
        },
        "tax_reconciliation": {
            "accounting_profit_before_tax": "100000.00",
            "adjustments": [
                {"key": "non_deductible", "amount": "5000.00", "treatment": "addition"},
                {"key": "exemption", "amount": "2000.00", "treatment": "deduction"},
            ],
        },
    }


def test_registry_contains_only_supported_engine_keys() -> None:
    assert {item.key for item in list_registered_engines()} == {
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


def test_every_registered_engine_executes_its_domain_adapter() -> None:
    for engine_key, payload in _payloads().items():
        execution = execute_registered_engine(engine_key=engine_key, payload=payload)

        assert execution.engine_key == engine_key
        assert execution.output_snapshot["engine_version"] == execution.engine_version
        assert execution.ruleset_snapshot == {
            "rule_versions": [],
            "regulatory_rules_applied": False,
            "current_rules_resolved": False,
        }


def test_tax_reconciliation_does_not_infer_current_tax() -> None:
    execution = execute_registered_engine(
        engine_key="tax_reconciliation",
        payload=_payloads()["tax_reconciliation"],
    )

    assert execution.output_snapshot["reconciled_taxable_base"] == "103000.00"
    assert execution.output_snapshot["taxable_base_inferred_from_accounting_profit"] is False
    assert "current_tax_expense" not in execution.output_snapshot
    assert execution.ruleset_snapshot["regulatory_rules_applied"] is False


def test_trade_and_ecommerce_are_distinct_keys_on_the_same_core_version() -> None:
    trade = execute_registered_engine(engine_key="trade", payload=_payloads()["trade"])
    ecommerce = execute_registered_engine(
        engine_key="ecommerce",
        payload=_payloads()["ecommerce"],
    )

    assert trade.engine_key == "trade"
    assert ecommerce.engine_key == "ecommerce"
    assert trade.engine_version == ecommerce.engine_version
    assert trade.output_snapshot == ecommerce.output_snapshot


def test_unknown_engine_fails_closed_without_dynamic_lookup() -> None:
    with pytest.raises(EngineNotFoundError, match="not registered"):
        execute_registered_engine(
            engine_key="os.system",
            payload={"command": "echo unsafe"},
        )


def test_continuous_numbers_must_arrive_as_decimal_strings() -> None:
    payload = _payloads()["food_manufacturing"].copy()
    payload["recipe_batches"] = 1.0

    with pytest.raises(EngineInputValidationError):
        execute_registered_engine(engine_key="food_manufacturing", payload=payload)


def test_non_finite_decimal_string_fails_closed() -> None:
    payload = _payloads()["trade"].copy()
    payload["sales"] = [
        {
            "key": "sale",
            "quantity": "NaN",
            "unit_sale_price": "100.00",
            "unit_acquisition_cost": "40.00",
        }
    ]

    with pytest.raises(EngineInputValidationError, match="finite"):
        execute_registered_engine(engine_key="trade", payload=payload)


def test_descriptor_exposes_schema_but_no_callable_or_import_target() -> None:
    descriptor = describe_registered_engine("transportation")

    assert descriptor.key == "transportation"
    assert descriptor.execution_requires_trusted_actor is True
    assert descriptor.regulatory_rules_applied is False
    assert descriptor.input_schema["type"] == "object"
    serialized = str(descriptor.input_schema)
    assert "executor" not in serialized
    assert "import" not in serialized.lower()
