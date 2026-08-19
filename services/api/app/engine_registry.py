"""Allowlisted calculation-engine registry and trusted execution boundary.

Engine selection is a closed mapping from stable keys to known Python callables.
No module path, function name, import target, or executable code is accepted
from caller input.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Callable, Mapping, cast
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app import (
    accommodation_engine,
    basic_metals_manufacturing,
    commerce_engine,
    food_manufacturing,
    textile_manufacturing,
    tourism_engine,
    transportation_engine,
)
from app.calculation_orchestration import record_calculation_version
from app.engine_contracts import (
    AccommodationEngineInput,
    BasicMetalsEngineInput,
    CommerceEngineInput,
    FoodEngineInput,
    TextileEngineInput,
    TourismEngineInput,
    TransportationEngineInput,
)
from app.manufacturing_engine import RecoveryCredit
from app.models import CalculationVersion


class EngineNotFoundError(LookupError):
    """Raised when a caller requests an engine outside the allowlist."""


class EngineInputValidationError(ValueError):
    """Raised when an allowlisted engine payload cannot be executed safely."""


@dataclass(frozen=True)
class EngineDescriptor:
    """Public, non-executable metadata for one registered engine."""

    key: str
    title: str
    engine_version: str
    input_schema: dict[str, object]
    execution_requires_trusted_actor: bool = True
    regulatory_rules_applied: bool = False


@dataclass(frozen=True)
class RegisteredExecution:
    """Canonical engine execution material ready for persistence."""

    engine_key: str
    engine_version: str
    input_snapshot: dict[str, object]
    ruleset_snapshot: dict[str, object]
    output_snapshot: dict[str, object]


Executor = Callable[[BaseModel], dict[str, object]]


@dataclass(frozen=True)
class RegisteredEngine:
    key: str
    title: str
    engine_version: str
    input_model: type[BaseModel]
    executor: Executor


def _decimal(value: str, *, field: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise EngineInputValidationError(f"{field} must be a decimal string") from exc
    if not parsed.is_finite():
        raise EngineInputValidationError(f"{field} must be finite")
    return parsed


def _recovery_credit(key: str, amount: str) -> RecoveryCredit:
    return RecoveryCredit(key=key, amount=_decimal(amount, field=f"recovery[{key}].amount"))


def _execute_food(model: BaseModel) -> dict[str, object]:
    if not isinstance(model, FoodEngineInput):
        raise EngineInputValidationError("food engine received the wrong input model")
    result = food_manufacturing.calculate_food_batch(
        output_unit=model.output_unit,
        recipe_batches=_decimal(model.recipe_batches, field="recipe_batches"),
        theoretical_output_per_recipe=_decimal(
            model.theoretical_output_per_recipe,
            field="theoretical_output_per_recipe",
        ),
        ingredients=tuple(
            food_manufacturing.RecipeIngredient(
                key=item.key,
                quantity_per_recipe=_decimal(
                    item.quantity_per_recipe,
                    field=f"ingredient[{item.key}].quantity_per_recipe",
                ),
                unit_cost=_decimal(item.unit_cost, field=f"ingredient[{item.key}].unit_cost"),
                unit=item.unit,
            )
            for item in model.ingredients
        ),
        package_count=model.package_count,
        package_content_quantity=_decimal(
            model.package_content_quantity,
            field="package_content_quantity",
        ),
        package_materials=tuple(
            food_manufacturing.PackageMaterial(
                key=item.key,
                quantity_per_package=_decimal(
                    item.quantity_per_package,
                    field=f"package_material[{item.key}].quantity_per_package",
                ),
                unit_cost=_decimal(
                    item.unit_cost,
                    field=f"package_material[{item.key}].unit_cost",
                ),
                unit=item.unit,
            )
            for item in model.package_materials
        ),
        process_costs=tuple(
            food_manufacturing.FoodProcessCost(
                key=item.key,
                category=item.category,
                amount=_decimal(item.amount, field=f"food_process[{item.key}].amount"),
            )
            for item in model.process_costs
        ),
        process_loss_quantity=_decimal(
            model.process_loss_quantity,
            field="process_loss_quantity",
        ),
        spoilage_quantity=_decimal(model.spoilage_quantity, field="spoilage_quantity"),
        quality_rejected_quantity=_decimal(
            model.quality_rejected_quantity,
            field="quality_rejected_quantity",
        ),
        recovery_credits=tuple(
            _recovery_credit(item.key, item.amount) for item in model.recovery_credits
        ),
    )
    return food_manufacturing.build_food_snapshot(result)


def _execute_textile(model: BaseModel) -> dict[str, object]:
    if not isinstance(model, TextileEngineInput):
        raise EngineInputValidationError("textile engine received the wrong input model")
    result = textile_manufacturing.calculate_textile_batch(
        theoretical_piece_count=model.theoretical_piece_count,
        cutting_reject_count=model.cutting_reject_count,
        quality_reject_count=model.quality_reject_count,
        ordered_piece_count=model.ordered_piece_count,
        materials=tuple(
            textile_manufacturing.TextileMaterial(
                key=item.key,
                category=item.category,
                quantity=_decimal(item.quantity, field=f"textile_material[{item.key}].quantity"),
                unit_cost=_decimal(
                    item.unit_cost,
                    field=f"textile_material[{item.key}].unit_cost",
                ),
                unit=item.unit,
            )
            for item in model.materials
        ),
        process_costs=tuple(
            textile_manufacturing.TextileProcessCost(
                key=item.key,
                stage=item.stage,
                cost_category=item.cost_category,
                amount=_decimal(item.amount, field=f"textile_process[{item.key}].amount"),
            )
            for item in model.process_costs
        ),
        recovery_credits=tuple(
            _recovery_credit(item.key, item.amount) for item in model.recovery_credits
        ),
    )
    return textile_manufacturing.build_textile_snapshot(result)


def _execute_basic_metals(model: BaseModel) -> dict[str, object]:
    if not isinstance(model, BasicMetalsEngineInput):
        raise EngineInputValidationError("basic-metals engine received the wrong input model")
    result = basic_metals_manufacturing.calculate_basic_metals_batch(
        output_unit=model.output_unit,
        theoretical_output_quantity=_decimal(
            model.theoretical_output_quantity,
            field="theoretical_output_quantity",
        ),
        melt_loss_quantity=_decimal(model.melt_loss_quantity, field="melt_loss_quantity"),
        slag_loss_quantity=_decimal(model.slag_loss_quantity, field="slag_loss_quantity"),
        quality_reject_quantity=_decimal(
            model.quality_reject_quantity,
            field="quality_reject_quantity",
        ),
        materials=tuple(
            basic_metals_manufacturing.MetalMaterial(
                key=item.key,
                category=item.category,
                quantity=_decimal(item.quantity, field=f"metal_material[{item.key}].quantity"),
                unit_cost=_decimal(item.unit_cost, field=f"metal_material[{item.key}].unit_cost"),
                unit=item.unit,
            )
            for item in model.materials
        ),
        energy_usages=tuple(
            basic_metals_manufacturing.MetalEnergyUsage(
                key=item.key,
                stage=item.stage,
                quantity=_decimal(item.quantity, field=f"metal_energy[{item.key}].quantity"),
                unit_rate=_decimal(item.unit_rate, field=f"metal_energy[{item.key}].unit_rate"),
                unit=item.unit,
            )
            for item in model.energy_usages
        ),
        process_costs=tuple(
            basic_metals_manufacturing.MetalProcessCost(
                key=item.key,
                stage=item.stage,
                cost_category=item.cost_category,
                amount=_decimal(item.amount, field=f"metal_process[{item.key}].amount"),
            )
            for item in model.process_costs
        ),
        recovered_scrap=tuple(
            basic_metals_manufacturing.RecoveredScrap(
                key=item.key,
                quantity=_decimal(item.quantity, field=f"recovered_scrap[{item.key}].quantity"),
                unit_value=_decimal(
                    item.unit_value,
                    field=f"recovered_scrap[{item.key}].unit_value",
                ),
                unit=item.unit,
            )
            for item in model.recovered_scrap
        ),
    )
    return basic_metals_manufacturing.build_basic_metals_snapshot(result)


def _execute_commerce(model: BaseModel) -> dict[str, object]:
    if not isinstance(model, CommerceEngineInput):
        raise EngineInputValidationError("commerce engine received the wrong input model")
    result = commerce_engine.calculate_commerce_result(
        sales=tuple(
            commerce_engine.CommerceSale(
                key=item.key,
                quantity=_decimal(item.quantity, field=f"sale[{item.key}].quantity"),
                unit_sale_price=_decimal(
                    item.unit_sale_price,
                    field=f"sale[{item.key}].unit_sale_price",
                ),
                unit_acquisition_cost=_decimal(
                    item.unit_acquisition_cost,
                    field=f"sale[{item.key}].unit_acquisition_cost",
                ),
                discount_amount=_decimal(
                    item.discount_amount,
                    field=f"sale[{item.key}].discount_amount",
                ),
                return_allowance_amount=_decimal(
                    item.return_allowance_amount,
                    field=f"sale[{item.key}].return_allowance_amount",
                ),
                inventory_recovery_credit=_decimal(
                    item.inventory_recovery_credit,
                    field=f"sale[{item.key}].inventory_recovery_credit",
                ),
            )
            for item in model.sales
        ),
        operating_costs=tuple(
            commerce_engine.CommerceOperatingCost(
                key=item.key,
                category=item.category,
                amount=_decimal(item.amount, field=f"operating_cost[{item.key}].amount"),
            )
            for item in model.operating_costs
        ),
        rate_fees=tuple(
            commerce_engine.CommerceRateFee(
                key=item.key,
                category=item.category,
                base_amount=_decimal(
                    item.base_amount,
                    field=f"rate_fee[{item.key}].base_amount",
                ),
                rate=_decimal(item.rate, field=f"rate_fee[{item.key}].rate"),
            )
            for item in model.rate_fees
        ),
        fixed_fees=tuple(
            commerce_engine.CommerceFixedFee(
                key=item.key,
                category=item.category,
                amount=_decimal(item.amount, field=f"fixed_fee[{item.key}].amount"),
            )
            for item in model.fixed_fees
        ),
    )
    return commerce_engine.build_commerce_snapshot(result)


def _execute_transportation(model: BaseModel) -> dict[str, object]:
    if not isinstance(model, TransportationEngineInput):
        raise EngineInputValidationError("transportation engine received the wrong input model")
    cargo = None
    if model.cargo is not None:
        cargo = transportation_engine.CargoLoad(
            quantity=_decimal(model.cargo.quantity, field="cargo.quantity"),
            unit=model.cargo.unit,
            capacity_quantity=(
                _decimal(model.cargo.capacity_quantity, field="cargo.capacity_quantity")
                if model.cargo.capacity_quantity is not None
                else None
            ),
        )
    result = transportation_engine.calculate_transportation_trip(
        distance=transportation_engine.TripDistance(
            loaded_km=_decimal(model.distance.loaded_km, field="distance.loaded_km"),
            empty_km=_decimal(model.distance.empty_km, field="distance.empty_km"),
        ),
        distance_consumptions=tuple(
            transportation_engine.DistanceConsumption(
                key=item.key,
                category=item.category,
                quantity_per_100_km=_decimal(
                    item.quantity_per_100_km,
                    field=f"distance_consumption[{item.key}].quantity_per_100_km",
                ),
                unit_price=_decimal(
                    item.unit_price,
                    field=f"distance_consumption[{item.key}].unit_price",
                ),
                unit=item.unit,
            )
            for item in model.distance_consumptions
        ),
        route_costs=tuple(
            transportation_engine.RouteTripCost(
                key=item.key,
                category=item.category,
                amount=_decimal(item.amount, field=f"route_cost[{item.key}].amount"),
            )
            for item in model.route_costs
        ),
        personnel_costs=tuple(
            transportation_engine.PersonnelTripCost(
                key=item.key,
                category=item.category,
                amount=_decimal(item.amount, field=f"personnel_cost[{item.key}].amount"),
            )
            for item in model.personnel_costs
        ),
        vehicle_costs=tuple(
            transportation_engine.VehicleAllocatedCost(
                key=item.key,
                category=item.category,
                amount=_decimal(item.amount, field=f"vehicle_cost[{item.key}].amount"),
            )
            for item in model.vehicle_costs
        ),
        cargo=cargo,
    )
    return transportation_engine.build_transportation_snapshot(result)


def _execute_accommodation(model: BaseModel) -> dict[str, object]:
    if not isinstance(model, AccommodationEngineInput):
        raise EngineInputValidationError("accommodation engine received the wrong input model")
    result = accommodation_engine.calculate_accommodation_result(
        capacity=accommodation_engine.AccommodationCapacity(
            available_rooms_per_night=model.capacity.available_rooms_per_night,
            nights=model.capacity.nights,
            occupied_room_nights=model.capacity.occupied_room_nights,
        ),
        channel_sales=tuple(
            accommodation_engine.AccommodationChannelSale(
                key=item.key,
                room_nights=item.room_nights,
                gross_room_revenue=_decimal(
                    item.gross_room_revenue,
                    field=f"channel_sale[{item.key}].gross_room_revenue",
                ),
                revenue_reduction_amount=_decimal(
                    item.revenue_reduction_amount,
                    field=f"channel_sale[{item.key}].revenue_reduction_amount",
                ),
                commission_base_amount=_decimal(
                    item.commission_base_amount,
                    field=f"channel_sale[{item.key}].commission_base_amount",
                ),
                commission_rate=_decimal(
                    item.commission_rate,
                    field=f"channel_sale[{item.key}].commission_rate",
                ),
                fixed_channel_fee=_decimal(
                    item.fixed_channel_fee,
                    field=f"channel_sale[{item.key}].fixed_channel_fee",
                ),
            )
            for item in model.channel_sales
        ),
        costs=tuple(
            accommodation_engine.AccommodationCost(
                key=item.key,
                category=item.category,
                scope=item.scope,
                amount=_decimal(item.amount, field=f"accommodation_cost[{item.key}].amount"),
            )
            for item in model.costs
        ),
    )
    return accommodation_engine.build_accommodation_snapshot(result)


def _execute_tourism(model: BaseModel) -> dict[str, object]:
    if not isinstance(model, TourismEngineInput):
        raise EngineInputValidationError("tourism engine received the wrong input model")
    result = tourism_engine.calculate_tourism_package(
        plan=tourism_engine.TourismPackagePlan(
            participant_count=model.plan.participant_count,
            currency=model.plan.currency,
        ),
        channel_sales=tuple(
            tourism_engine.TourismChannelSale(
                key=item.key,
                participant_count=item.participant_count,
                gross_revenue=_decimal(
                    item.gross_revenue,
                    field=f"channel_sale[{item.key}].gross_revenue",
                ),
                revenue_reduction_amount=_decimal(
                    item.revenue_reduction_amount,
                    field=f"channel_sale[{item.key}].revenue_reduction_amount",
                ),
                commission_base_amount=_decimal(
                    item.commission_base_amount,
                    field=f"channel_sale[{item.key}].commission_base_amount",
                ),
                commission_rate=_decimal(
                    item.commission_rate,
                    field=f"channel_sale[{item.key}].commission_rate",
                ),
                fixed_channel_fee=_decimal(
                    item.fixed_channel_fee,
                    field=f"channel_sale[{item.key}].fixed_channel_fee",
                ),
            )
            for item in model.channel_sales
        ),
        components=tuple(
            tourism_engine.TourismComponentCost(
                key=item.key,
                category=item.category,
                scope=item.scope,
                amount=_decimal(item.amount, field=f"component[{item.key}].amount"),
            )
            for item in model.components
        ),
    )
    return tourism_engine.build_tourism_snapshot(result)


_ENGINE_REGISTRY: Mapping[str, RegisteredEngine] = MappingProxyType(
    {
        "food_manufacturing": RegisteredEngine(
            key="food_manufacturing",
            title="Gıda üretimi",
            engine_version=food_manufacturing.ENGINE_VERSION,
            input_model=FoodEngineInput,
            executor=_execute_food,
        ),
        "textile_manufacturing": RegisteredEngine(
            key="textile_manufacturing",
            title="Tekstil üretimi",
            engine_version=textile_manufacturing.ENGINE_VERSION,
            input_model=TextileEngineInput,
            executor=_execute_textile,
        ),
        "basic_metals": RegisteredEngine(
            key="basic_metals",
            title="Ana metal üretimi",
            engine_version=basic_metals_manufacturing.ENGINE_VERSION,
            input_model=BasicMetalsEngineInput,
            executor=_execute_basic_metals,
        ),
        "ecommerce": RegisteredEngine(
            key="ecommerce",
            title="E-ticaret",
            engine_version=commerce_engine.ENGINE_VERSION,
            input_model=CommerceEngineInput,
            executor=_execute_commerce,
        ),
        "trade": RegisteredEngine(
            key="trade",
            title="Ticaret",
            engine_version=commerce_engine.ENGINE_VERSION,
            input_model=CommerceEngineInput,
            executor=_execute_commerce,
        ),
        "transportation": RegisteredEngine(
            key="transportation",
            title="Ulaştırma / lojistik",
            engine_version=transportation_engine.ENGINE_VERSION,
            input_model=TransportationEngineInput,
            executor=_execute_transportation,
        ),
        "accommodation": RegisteredEngine(
            key="accommodation",
            title="Konaklama",
            engine_version=accommodation_engine.ENGINE_VERSION,
            input_model=AccommodationEngineInput,
            executor=_execute_accommodation,
        ),
        "tourism": RegisteredEngine(
            key="tourism",
            title="Turizm paketi",
            engine_version=tourism_engine.ENGINE_VERSION,
            input_model=TourismEngineInput,
            executor=_execute_tourism,
        ),
    }
)


def get_registered_engine(engine_key: str) -> RegisteredEngine:
    """Resolve one engine only from the closed registry."""

    try:
        return _ENGINE_REGISTRY[engine_key]
    except KeyError as exc:
        raise EngineNotFoundError(f"engine is not registered: {engine_key}") from exc


def describe_registered_engine(engine_key: str) -> EngineDescriptor:
    """Return public schema metadata without exposing a callable/import target."""

    engine = get_registered_engine(engine_key)
    schema = cast(dict[str, object], engine.input_model.model_json_schema())
    return EngineDescriptor(
        key=engine.key,
        title=engine.title,
        engine_version=engine.engine_version,
        input_schema=schema,
    )


def list_registered_engines() -> tuple[EngineDescriptor, ...]:
    """List deterministic public descriptors for all allowlisted engines."""

    return tuple(describe_registered_engine(key) for key in sorted(_ENGINE_REGISTRY))


def execute_registered_engine(
    *,
    engine_key: str,
    payload: dict[str, object],
) -> RegisteredExecution:
    """Validate and execute one allowlisted engine without persistence."""

    engine = get_registered_engine(engine_key)
    try:
        model = engine.input_model.model_validate(payload)
        output_snapshot = engine.executor(model)
    except ValidationError as exc:
        raise EngineInputValidationError(str(exc)) from exc
    except EngineInputValidationError:
        raise
    except ValueError as exc:
        raise EngineInputValidationError(str(exc)) from exc

    input_snapshot = cast(dict[str, object], model.model_dump(mode="json"))
    return RegisteredExecution(
        engine_key=engine.key,
        engine_version=engine.engine_version,
        input_snapshot=input_snapshot,
        ruleset_snapshot={
            "rule_versions": [],
            "regulatory_rules_applied": False,
            "current_rules_resolved": False,
        },
        output_snapshot=output_snapshot,
    )


def execute_and_record_registered_engine(
    session: Session,
    *,
    organization_id: UUID,
    calculation_id: UUID,
    created_by_user_id: UUID,
    engine_key: str,
    payload: dict[str, object],
) -> tuple[CalculationVersion, RegisteredExecution]:
    """Execute then persist through the trusted tenant orchestration layer."""

    execution = execute_registered_engine(engine_key=engine_key, payload=payload)
    version = record_calculation_version(
        session,
        organization_id=organization_id,
        calculation_id=calculation_id,
        created_by_user_id=created_by_user_id,
        engine_key=execution.engine_key,
        engine_version=execution.engine_version,
        input_snapshot=execution.input_snapshot,
        ruleset_snapshot=execution.ruleset_snapshot,
        output_snapshot=execution.output_snapshot,
    )
    return version, execution
