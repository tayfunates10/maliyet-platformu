"""Contract tests for strict regulated personnel-cost inputs."""

import pytest
from pydantic import ValidationError

from app.personnel_cost_contracts import PersonnelCostInput


def test_personnel_cost_contract_accepts_json_cost_array() -> None:
    model = PersonnelCostInput.model_validate(
        {
            "at_date": "2026-08-19",
            "gross_cash_compensation": "50000.00",
            "declared_monthly_earnings": "50000.00",
            "additional_employer_costs": [{"key": "meal", "amount": "1000.00"}],
        }
    )

    assert len(model.additional_employer_costs) == 1
    assert model.additional_employer_costs[0].amount == "1000.00"


def test_personnel_cost_contract_rejects_numeric_money_and_rate_override() -> None:
    with pytest.raises(ValidationError):
        PersonnelCostInput.model_validate(
            {
                "at_date": "2026-08-19",
                "gross_cash_compensation": 50000.0,
                "declared_monthly_earnings": "50000.00",
                "additional_employer_costs": [],
            }
        )

    with pytest.raises(ValidationError):
        PersonnelCostInput.model_validate(
            {
                "at_date": "2026-08-19",
                "gross_cash_compensation": "50000.00",
                "declared_monthly_earnings": "50000.00",
                "additional_employer_costs": [],
                "employer_sgk_rate": "0.01",
            }
        )


def test_personnel_cost_contract_rejects_unbounded_decimal_forms() -> None:
    for invalid in ("1e1000000", "9" * 39, "0." + "1" * 19):
        with pytest.raises(ValidationError):
            PersonnelCostInput.model_validate(
                {
                    "at_date": "2026-08-19",
                    "gross_cash_compensation": invalid,
                    "declared_monthly_earnings": "50000.00",
                    "additional_employer_costs": [],
                }
            )
