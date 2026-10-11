"""Estimate needs from location severity and affected population.

Pure function over a fixed configuration table. Missing inputs are listed and
nothing is estimated for them: the function never guesses severity or population.
Estimates are advisory; they are not confirmed needs.
"""

from math import ceil

from pydantic import BaseModel, ConfigDict

from app.models.affected_location import AffectedLocation, SeverityLevel
from app.models.resource_need import NeedType

# need type -> (unit, people per unit, minimum severity that triggers it)
# Planning ratios for demo use; replace with the agency's own standards.
NEED_RATES: dict[NeedType, tuple[str, float, SeverityLevel]] = {
    NeedType.DRINKING_WATER: ("litres", 1 / 15, SeverityLevel.LOW),   # 15 L per person per day
    NeedType.FOOD: ("kits", 5, SeverityLevel.MODERATE),              # 1 ration kit per household of 5
    NeedType.MEDICAL: ("kits", 50, SeverityLevel.MODERATE),
    NeedType.SHELTER: ("kits", 5, SeverityLevel.HIGH),
    NeedType.RESCUE: ("boats", 200, SeverityLevel.HIGH),
}

_SEVERITY_ORDER = [
    SeverityLevel.LOW, SeverityLevel.MODERATE, SeverityLevel.HIGH, SeverityLevel.CRITICAL,
]


class EstimatedNeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str
    need_type: NeedType
    quantity: float
    quantity_unit: str
    basis: str


class NeedEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    needs: list[EstimatedNeed]
    missing_inputs: list[str]


def estimate_needs(locations: list[AffectedLocation]) -> NeedEstimate:
    needs: list[EstimatedNeed] = []
    missing: list[str] = []
    for location in sorted(locations, key=lambda loc: loc.location_id):
        gaps = []
        if location.severity == SeverityLevel.UNKNOWN:
            gaps.append("severity")
        if location.population_affected is None:
            gaps.append("population_affected")
        if gaps:
            missing.append(f"{location.location_id}: {', '.join(gaps)}")
            continue
        assert location.population_affected is not None
        rank = _SEVERITY_ORDER.index(location.severity)
        for need_type, (unit, people_per_unit, minimum) in NEED_RATES.items():
            if rank < _SEVERITY_ORDER.index(minimum):
                continue
            quantity = float(ceil(location.population_affected / people_per_unit))
            if quantity <= 0:
                continue
            needs.append(EstimatedNeed(
                location_id=location.location_id,
                need_type=need_type,
                quantity=quantity,
                quantity_unit=unit,
                basis=(
                    f"{location.population_affected} people at {location.severity} severity; "
                    f"1 {unit.rstrip('s')} per {people_per_unit:g} people."
                    if people_per_unit >= 1 else
                    f"{location.population_affected} people at {location.severity} severity; "
                    f"{1 / people_per_unit:g} {unit} per person."
                ),
            ))
    return NeedEstimate(needs=needs, missing_inputs=missing)
