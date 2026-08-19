"""Trade and e-commerce order-economics primitives.

The engine calculates management contribution without inventing marketplace,
payment, VAT, tax, or return rules. Every percentage charge carries an explicit
monetary base supplied by the caller.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

ENGINE_VERSION = "commerce-ecommerce-core-v1"
ZERO = Decimal("0")
ONE = Decimal("1")

OPERATING_COST_CATEGORIES = frozenset(
    {
        "inbound_freight",
        "fulfillment",
        "packaging",
        "storage",
        "advertising",
        "return_handling",
        "other",
    }
)

FEE_CATEGORIES = frozenset(
    {
        "marketplace_commission",
        "payment_fee",
        "channel_fee",
        "other",
    }
)


class CommerceInputError(ValueError):
    """Raised when trade/e-commerce inputs violate explicit cost contracts."""


def _require_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise CommerceInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise CommerceInputError(f"{field} must be finite")
    return value


def _require_non_negative(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value < ZERO:
        raise CommerceInputError(f"{field} must be non-negative")
    return decimal_value


def _require_positive(value: object, *, field: str) -> Decimal:
    decimal_value = _require_decimal(value, field=field)
    if decimal_value <= ZERO:
        raise CommerceInputError(f"{field} must be positive")
    return decimal_value


def _require_rate(value: object, *, field: str) -> Decimal:
    decimal_value = _require_non_negative(value, field=field)
    if decimal_value >= ONE:
        raise CommerceInputError(f"{field} must be less than 1")
    return decimal_value


def _require_key(value: str, *, field: str) -> None:
    if not value.strip():
        raise CommerceInputError(f"{field} must not be blank")


@dataclass(frozen=True)
class CommerceSale:
    """One homogeneous sale quantity with explicit management revenue reductions."""

    key: str
    quantity: Decimal
    unit_sale_price: Decimal
    unit_acquisition_cost: Decimal
    discount_amount: Decimal = ZERO
    return_allowance_amount: Decimal = ZERO
    inventory_recovery_credit: Decimal = ZERO

    def __post_init__(self) -> None:
        _require_key(self.key, field="sale.key")
        _require_positive(self.quantity, field=f"sale[{self.key}].quantity")
        _require_non_negative(self.unit_sale_price, field=f"sale[{self.key}].unit_sale_price")
        _require_non_negative(
            self.unit_acquisition_cost,
            field=f"sale[{self.key}].unit_acquisition_cost",
        )
        discount = _require_non_negative(
            self.discount_amount,
            field=f"sale[{self.key}].discount_amount",
        )
        return_allowance = _require_non_negative(
            self.return_allowance_amount,
            field=f"sale[{self.key}].return_allowance_amount",
        )
        gross = self.quantity * self.unit_sale_price
        if discount + return_allowance > gross:
            raise CommerceInputError(
                f"sale[{self.key}] revenue reductions cannot exceed gross sales"
            )
        recovery = _require_non_negative(
            self.inventory_recovery_credit,
            field=f"sale[{self.key}].inventory_recovery_credit",
        )
        acquisition = self.quantity * self.unit_acquisition_cost
        if recovery > acquisition:
            raise CommerceInputError(
                f"sale[{self.key}] inventory recovery credit cannot exceed acquisition cost"
            )

    @property
    def gross_sales(self) -> Decimal:
        return self.quantity * self.unit_sale_price

    @property
    def revenue_reductions(self) -> Decimal:
        return self.discount_amount + self.return_allowance_amount

    @property
    def net_sales(self) -> Decimal:
        return self.gross_sales - self.revenue_reductions

    @property
    def gross_acquisition_cost(self) -> Decimal:
        return self.quantity * self.unit_acquisition_cost

    @property
    def net_acquisition_cost(self) -> Decimal:
        return self.gross_acquisition_cost - self.inventory_recovery_credit


@dataclass(frozen=True)
class CommerceOperatingCost:
    """Explicit non-product operating cost allocated to the sale/order."""

    key: str
    category: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="operating_cost.key")
        if self.category not in OPERATING_COST_CATEGORIES:
            raise CommerceInputError(f"unsupported operating cost category: {self.category}")
        _require_non_negative(self.amount, field=f"operating_cost[{self.key}].amount")


@dataclass(frozen=True)
class CommerceRateFee:
    """Percentage fee with caller-supplied monetary base and explicit rate."""

    key: str
    category: str
    base_amount: Decimal
    rate: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="rate_fee.key")
        if self.category not in FEE_CATEGORIES:
            raise CommerceInputError(f"unsupported fee category: {self.category}")
        _require_non_negative(self.base_amount, field=f"rate_fee[{self.key}].base_amount")
        _require_rate(self.rate, field=f"rate_fee[{self.key}].rate")

    @property
    def amount(self) -> Decimal:
        return self.base_amount * self.rate


@dataclass(frozen=True)
class CommerceFixedFee:
    """Fixed marketplace/payment/channel charge allocated to the sale/order."""

    key: str
    category: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_key(self.key, field="fixed_fee.key")
        if self.category not in FEE_CATEGORIES:
            raise CommerceInputError(f"unsupported fee category: {self.category}")
        _require_non_negative(self.amount, field=f"fixed_fee[{self.key}].amount")


@dataclass(frozen=True)
class CommerceResult:
    """Management contribution result before VAT/tax/legal accounting policies."""

    gross_sales: Decimal
    discount_amount: Decimal
    return_allowance_amount: Decimal
    net_sales: Decimal
    gross_acquisition_cost: Decimal
    inventory_recovery_credit: Decimal
    net_acquisition_cost: Decimal
    operating_cost: Decimal
    operating_category_costs: tuple[tuple[str, Decimal], ...]
    rate_fee_cost: Decimal
    fixed_fee_cost: Decimal
    fee_category_costs: tuple[tuple[str, Decimal], ...]
    total_channel_cost: Decimal
    contribution_profit: Decimal
    contribution_margin_ratio: Decimal | None


def _ensure_unique_keys(
    items: Iterable[CommerceSale | CommerceOperatingCost | CommerceRateFee | CommerceFixedFee],
) -> None:
    seen: set[str] = set()
    for item in items:
        if item.key in seen:
            raise CommerceInputError(f"duplicate commerce line key: {item.key}")
        seen.add(item.key)


def _operating_category_totals(
    costs: Sequence[CommerceOperatingCost],
) -> tuple[tuple[str, Decimal], ...]:
    totals: dict[str, Decimal] = {}
    for line in costs:
        totals[line.category] = totals.get(line.category, ZERO) + line.amount
    return tuple(sorted(totals.items()))


def _fee_category_totals(
    rate_fees: Sequence[CommerceRateFee],
    fixed_fees: Sequence[CommerceFixedFee],
) -> tuple[tuple[str, Decimal], ...]:
    totals: dict[str, Decimal] = {}
    for rate_fee in rate_fees:
        totals[rate_fee.category] = totals.get(rate_fee.category, ZERO) + rate_fee.amount
    for fixed_fee in fixed_fees:
        totals[fixed_fee.category] = totals.get(fixed_fee.category, ZERO) + fixed_fee.amount
    return tuple(sorted(totals.items()))


def calculate_commerce_result(
    *,
    sales: Sequence[CommerceSale],
    operating_costs: Sequence[CommerceOperatingCost],
    rate_fees: Sequence[CommerceRateFee],
    fixed_fees: Sequence[CommerceFixedFee],
) -> CommerceResult:
    """Calculate trade/e-commerce contribution from fully explicit charges."""

    if not sales:
        raise CommerceInputError("at least one sale line is required")
    _ensure_unique_keys((*sales, *operating_costs, *rate_fees, *fixed_fees))

    gross_sales = sum((line.gross_sales for line in sales), ZERO)
    discount_amount = sum((line.discount_amount for line in sales), ZERO)
    return_allowance_amount = sum((line.return_allowance_amount for line in sales), ZERO)
    net_sales = gross_sales - discount_amount - return_allowance_amount
    gross_acquisition_cost = sum((line.gross_acquisition_cost for line in sales), ZERO)
    inventory_recovery_credit = sum((line.inventory_recovery_credit for line in sales), ZERO)
    net_acquisition_cost = gross_acquisition_cost - inventory_recovery_credit
    operating_cost = sum((line.amount for line in operating_costs), ZERO)
    rate_fee_cost = sum((line.amount for line in rate_fees), ZERO)
    fixed_fee_cost = sum((line.amount for line in fixed_fees), ZERO)
    total_channel_cost = rate_fee_cost + fixed_fee_cost
    contribution_profit = net_sales - net_acquisition_cost - operating_cost - total_channel_cost
    contribution_margin_ratio = contribution_profit / net_sales if net_sales != ZERO else None

    return CommerceResult(
        gross_sales=gross_sales,
        discount_amount=discount_amount,
        return_allowance_amount=return_allowance_amount,
        net_sales=net_sales,
        gross_acquisition_cost=gross_acquisition_cost,
        inventory_recovery_credit=inventory_recovery_credit,
        net_acquisition_cost=net_acquisition_cost,
        operating_cost=operating_cost,
        operating_category_costs=_operating_category_totals(operating_costs),
        rate_fee_cost=rate_fee_cost,
        fixed_fee_cost=fixed_fee_cost,
        fee_category_costs=_fee_category_totals(rate_fees, fixed_fees),
        total_channel_cost=total_channel_cost,
        contribution_profit=contribution_profit,
        contribution_margin_ratio=contribution_margin_ratio,
    )


def build_commerce_snapshot(result: CommerceResult) -> dict[str, object]:
    """Serialize exact management economics without inventing regulatory rules."""

    return {
        "engine_version": ENGINE_VERSION,
        "gross_sales": str(result.gross_sales),
        "discount_amount": str(result.discount_amount),
        "return_allowance_amount": str(result.return_allowance_amount),
        "net_sales": str(result.net_sales),
        "gross_acquisition_cost": str(result.gross_acquisition_cost),
        "inventory_recovery_credit": str(result.inventory_recovery_credit),
        "net_acquisition_cost": str(result.net_acquisition_cost),
        "operating_cost": str(result.operating_cost),
        "operating_category_costs": {
            category: str(amount) for category, amount in result.operating_category_costs
        },
        "rate_fee_cost": str(result.rate_fee_cost),
        "fixed_fee_cost": str(result.fixed_fee_cost),
        "fee_category_costs": {
            category: str(amount) for category, amount in result.fee_category_costs
        },
        "total_channel_cost": str(result.total_channel_cost),
        "contribution_profit": str(result.contribution_profit),
        "contribution_margin_ratio": (
            str(result.contribution_margin_ratio)
            if result.contribution_margin_ratio is not None
            else None
        ),
        "marketplace_fee_schedule_inferred": False,
        "payment_fee_schedule_inferred": False,
        "return_probability_inferred": False,
        "vat_treatment_applied": False,
        "tax_policy_applied": False,
        "inventory_valuation_policy_applied": False,
    }
