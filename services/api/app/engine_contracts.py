"""Strict API-facing input contracts for allowlisted calculation engines.

Continuous quantities and monetary values are represented as strings so JSON
transport never silently converts them through binary floating point. Domain
engines convert these strings to Decimal at the execution boundary.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Base model that rejects coercion and unknown fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RecoveryCreditInput(ContractModel):
    key: str
    amount: str


class FoodIngredientInput(ContractModel):
    key: str
    quantity_per_recipe: str
    unit_cost: str
    unit: str


class FoodPackageMaterialInput(ContractModel):
    key: str
    quantity_per_package: str
    unit_cost: str
    unit: str


class FoodProcessCostInput(ContractModel):
    key: str
    category: Literal[
        "labor",
        "energy",
        "cold_chain",
        "quality",
        "packaging",
        "subcontracting",
        "other",
    ]
    amount: str


class FoodEngineInput(ContractModel):
    output_unit: str
    recipe_batches: str
    theoretical_output_per_recipe: str
    ingredients: list[FoodIngredientInput] = Field(default_factory=list)
    package_count: int
    package_content_quantity: str
    package_materials: list[FoodPackageMaterialInput] = Field(default_factory=list)
    process_costs: list[FoodProcessCostInput] = Field(default_factory=list)
    process_loss_quantity: str = "0"
    spoilage_quantity: str = "0"
    quality_rejected_quantity: str = "0"
    recovery_credits: list[RecoveryCreditInput] = Field(default_factory=list)


class TextileMaterialInput(ContractModel):
    key: str
    category: Literal[
        "fabric",
        "yarn",
        "lining",
        "accessory",
        "chemical",
        "packaging",
        "other",
    ]
    quantity: str
    unit_cost: str
    unit: str


class TextileProcessCostInput(ContractModel):
    key: str
    stage: Literal[
        "cutting",
        "sewing",
        "dyeing",
        "printing",
        "embroidery",
        "finishing",
        "ironing",
        "packaging",
        "quality",
        "other",
    ]
    cost_category: Literal[
        "labor",
        "energy",
        "machine",
        "packaging",
        "subcontracting",
        "quality",
        "other",
    ]
    amount: str


class TextileEngineInput(ContractModel):
    theoretical_piece_count: int
    cutting_reject_count: int
    quality_reject_count: int
    ordered_piece_count: int
    materials: list[TextileMaterialInput] = Field(default_factory=list)
    process_costs: list[TextileProcessCostInput] = Field(default_factory=list)
    recovery_credits: list[RecoveryCreditInput] = Field(default_factory=list)


class MetalMaterialInput(ContractModel):
    key: str
    category: Literal[
        "primary_metal",
        "recycled_charge",
        "alloy",
        "flux",
        "electrode",
        "refractory",
        "consumable",
        "packaging",
        "other",
    ]
    quantity: str
    unit_cost: str
    unit: str


class MetalEnergyUsageInput(ContractModel):
    key: str
    stage: Literal[
        "melting",
        "reheating",
        "heat_treatment",
        "casting",
        "rolling",
        "other",
    ]
    quantity: str
    unit_rate: str
    unit: str


class MetalProcessCostInput(ContractModel):
    key: str
    stage: Literal[
        "melting",
        "casting",
        "rolling",
        "forging",
        "heat_treatment",
        "machining",
        "finishing",
        "quality",
        "packaging",
        "other",
    ]
    cost_category: Literal[
        "labor",
        "energy",
        "machine",
        "packaging",
        "subcontracting",
        "quality",
        "other",
    ]
    amount: str


class RecoveredScrapInput(ContractModel):
    key: str
    quantity: str
    unit_value: str
    unit: str


class BasicMetalsEngineInput(ContractModel):
    output_unit: str
    theoretical_output_quantity: str
    melt_loss_quantity: str
    slag_loss_quantity: str
    quality_reject_quantity: str
    materials: list[MetalMaterialInput] = Field(default_factory=list)
    energy_usages: list[MetalEnergyUsageInput] = Field(default_factory=list)
    process_costs: list[MetalProcessCostInput] = Field(default_factory=list)
    recovered_scrap: list[RecoveredScrapInput] = Field(default_factory=list)


class CommerceSaleInput(ContractModel):
    key: str
    quantity: str
    unit_sale_price: str
    unit_acquisition_cost: str
    discount_amount: str = "0"
    return_allowance_amount: str = "0"
    inventory_recovery_credit: str = "0"


class CommerceOperatingCostInput(ContractModel):
    key: str
    category: Literal[
        "inbound_freight",
        "fulfillment",
        "packaging",
        "storage",
        "advertising",
        "return_handling",
        "other",
    ]
    amount: str


class CommerceRateFeeInput(ContractModel):
    key: str
    category: Literal[
        "marketplace_commission",
        "payment_fee",
        "channel_fee",
        "other",
    ]
    base_amount: str
    rate: str


class CommerceFixedFeeInput(ContractModel):
    key: str
    category: Literal[
        "marketplace_commission",
        "payment_fee",
        "channel_fee",
        "other",
    ]
    amount: str


class CommerceEngineInput(ContractModel):
    sales: list[CommerceSaleInput]
    operating_costs: list[CommerceOperatingCostInput] = Field(default_factory=list)
    rate_fees: list[CommerceRateFeeInput] = Field(default_factory=list)
    fixed_fees: list[CommerceFixedFeeInput] = Field(default_factory=list)


class TripDistanceInput(ContractModel):
    loaded_km: str
    empty_km: str


class DistanceConsumptionInput(ContractModel):
    key: str
    category: Literal["fuel", "adblue", "other"]
    quantity_per_100_km: str
    unit_price: str
    unit: str


class RouteTripCostInput(ContractModel):
    key: str
    category: Literal[
        "toll",
        "bridge",
        "ferry",
        "parking",
        "loading",
        "unloading",
        "other",
    ]
    amount: str


class PersonnelTripCostInput(ContractModel):
    key: str
    category: Literal[
        "driver_labor",
        "assistant_labor",
        "per_diem",
        "accommodation",
        "other",
    ]
    amount: str


class VehicleAllocatedCostInput(ContractModel):
    key: str
    category: Literal[
        "maintenance",
        "tyre",
        "insurance",
        "depreciation",
        "financing",
        "other",
    ]
    amount: str


class CargoLoadInput(ContractModel):
    quantity: str
    unit: str
    capacity_quantity: str | None = None


class TransportationEngineInput(ContractModel):
    distance: TripDistanceInput
    distance_consumptions: list[DistanceConsumptionInput] = Field(default_factory=list)
    route_costs: list[RouteTripCostInput] = Field(default_factory=list)
    personnel_costs: list[PersonnelTripCostInput] = Field(default_factory=list)
    vehicle_costs: list[VehicleAllocatedCostInput] = Field(default_factory=list)
    cargo: CargoLoadInput | None = None


class AccommodationCapacityInput(ContractModel):
    available_rooms_per_night: int
    nights: int
    occupied_room_nights: int


class AccommodationChannelSaleInput(ContractModel):
    key: str
    room_nights: int
    gross_room_revenue: str
    revenue_reduction_amount: str = "0"
    commission_base_amount: str = "0"
    commission_rate: str = "0"
    fixed_channel_fee: str = "0"


class AccommodationCostInput(ContractModel):
    key: str
    category: Literal[
        "housekeeping",
        "laundry",
        "amenity",
        "breakfast",
        "energy",
        "water",
        "maintenance",
        "personnel",
        "software",
        "marketing",
        "other",
    ]
    scope: Literal["occupied_variable", "period_fixed"]
    amount: str


class AccommodationEngineInput(ContractModel):
    capacity: AccommodationCapacityInput
    channel_sales: list[AccommodationChannelSaleInput] = Field(default_factory=list)
    costs: list[AccommodationCostInput] = Field(default_factory=list)


class TourismPackagePlanInput(ContractModel):
    participant_count: int
    currency: str


class TourismChannelSaleInput(ContractModel):
    key: str
    participant_count: int
    gross_revenue: str
    revenue_reduction_amount: str = "0"
    commission_base_amount: str = "0"
    commission_rate: str = "0"
    fixed_channel_fee: str = "0"


class TourismComponentCostInput(ContractModel):
    key: str
    category: Literal[
        "transportation",
        "accommodation",
        "guide",
        "transfer",
        "meal",
        "ticket",
        "activity",
        "insurance",
        "other",
    ]
    scope: Literal["per_participant", "fixed_package"]
    amount: str


class TourismEngineInput(ContractModel):
    plan: TourismPackagePlanInput
    channel_sales: list[TourismChannelSaleInput]
    components: list[TourismComponentCostInput] = Field(default_factory=list)
