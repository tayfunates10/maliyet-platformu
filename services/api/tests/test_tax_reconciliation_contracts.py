"""Contract tests for strict tax reconciliation HTTP inputs."""

import pytest
from pydantic import ValidationError

from app.tax_reconciliation_contracts import TaxReconciliationInput


def test_tax_reconciliation_contract_accepts_json_adjustment_array() -> None:
    model = TaxReconciliationInput.model_validate(
        {
            "accounting_profit_before_tax": "100000.00",
            "adjustments": [
                {"key": "non_deductible", "amount": "5000.00", "treatment": "addition"}
            ],
        }
    )

    assert len(model.adjustments) == 1
    assert model.adjustments[0].amount == "5000.00"


def test_tax_reconciliation_contract_rejects_numeric_money() -> None:
    with pytest.raises(ValidationError):
        TaxReconciliationInput.model_validate(
            {
                "accounting_profit_before_tax": 100000.0,
                "adjustments": [],
            }
        )


def test_tax_reconciliation_contract_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TaxReconciliationInput.model_validate(
            {
                "accounting_profit_before_tax": "100000.00",
                "adjustments": [],
                "tax_rate": "0.25",
            }
        )
