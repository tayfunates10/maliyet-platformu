"""Contract tests for strict tax reconciliation HTTP inputs."""

import pytest
from pydantic import ValidationError

from app.tax_reconciliation_contracts import TaxReconciliationInput


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
