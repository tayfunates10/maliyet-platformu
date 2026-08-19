# ADR 0012 — Transportation trip-cost engine

## Status

Accepted for PR #13.

## Context

Transportation profitability cannot be reduced to `distance × fuel`. A trip may contain loaded and empty kilometres, multiple distance-based consumables, toll/bridge/ferry charges, loading/unloading costs, personnel allocations and vehicle costs such as maintenance, tyres, insurance, depreciation and financing.

External values also change frequently. Fuel prices, toll schedules, route distance, payroll treatment and depreciation policies must not be silently inferred or hard-coded into the trip-cost kernel.

Cargo economics introduce another unit-safety concern. Ton-kilometre is meaningful only when cargo is explicitly measured in tonnes. Pallets, cubic metres, kilograms or other units must not be converted silently.

## Decision

1. Loaded and empty kilometres are explicit caller-supplied Decimal values; total distance is their exact sum.
2. Total trip distance must be positive. Loaded distance may be zero, in which case loaded-km unit cost is unavailable rather than fabricated.
3. Fuel, AdBlue and other distance consumables are modeled as explicit `quantity_per_100_km × total_km / 100 × unit_price` inputs.
4. The engine never fetches or infers fuel/AdBlue prices.
5. Toll, bridge, ferry, parking, loading and unloading costs are explicit trip amounts.
6. Personnel costs are explicit trip allocations; this kernel does not infer net-to-gross payroll, SGK or legal driving-hour treatment.
7. Vehicle maintenance, tyre, insurance, depreciation and financing are explicit trip allocations supplied by an upstream policy. No depreciation life/rate is inferred here.
8. Cargo quantity and optional capacity must use one explicit caller-supplied unit. Capacity utilization is calculated only from those same-unit values.
9. Ton-km and cost-per-ton-km are produced only when `cargo.unit == "ton"`. No kg/m3/pallet conversion is attempted.
10. Cost per cargo unit is calculated directly from explicit cargo quantity regardless of unit label.
11. Duplicate keys across all transportation cost groups fail closed to keep audit lines unambiguous.
12. All monetary and continuous-quantity calculations use `Decimal`; binary floats fail closed.
13. The resulting total trip cost can be bridged into the sector-neutral costing engine as a direct `CostLine`.
14. Snapshots explicitly state that route distance, fuel price, toll schedule, payroll policy, depreciation policy and legal driving-hour policy were not inferred/applied.

## Consequences

- Empty running is visible in the same trip economics instead of being hidden.
- Fuel and AdBlue costs remain reproducible because both consumption rate and price are explicit inputs.
- External price integrations can be added later without changing the cost kernel.
- Ton-km reporting cannot accidentally convert incompatible cargo units.
- Payroll, vehicle depreciation and regulatory driving-time rules remain separate source-backed/upstream layers.

## Follow-up

After this engine is green and merged, the next sector module is accommodation: room-night capacity, occupancy, channel commissions, housekeeping/laundry/amenity/energy allocations, occupied-room cost, available-room cost and room contribution economics without hard-coding the accommodation-tax treatment.
