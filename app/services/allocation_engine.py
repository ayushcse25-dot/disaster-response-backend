from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.affected_location import AffectedLocation
from app.models.enums import EventStatus, EventVerificationStatus
from app.models.flood_event import FloodEvent
from app.models.resource_inventory import (
    InventoryStatus,
    ResourceInventory,
    ResourceType,
)
from app.models.resource_need import NeedStatus, NeedType, ResourceNeed
from app.models.response_team import (
    ResponseTeam,
    TeamCapability,
    TeamStatus,
)


ALGORITHM_VERSION = "1.0.0"

# These are conservative defaults, not claims that the data is accurate.
DEFAULT_INVENTORY_MAX_AGE = timedelta(hours=24)
DEFAULT_TEAM_STATUS_MAX_AGE = timedelta(hours=2)


class AllocationDecision(BaseModel):
    """An explainable proposal; never an approval or dispatch."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    need_id: str
    location_id: str
    inventory_id: str
    team_id: str

    proposed_quantity: float = Field(gt=0)
    quantity_unit: str

    status: Literal["PROPOSED"] = "PROPOSED"
    algorithm_version: str = ALGORITHM_VERSION

    rationale: list[str]
    constraints: list[str] = Field(default_factory=list)
    unresolved_uncertainties: list[str] = Field(default_factory=list)


class UnallocatedNeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    need_id: str
    reasons: list[str]


class AllocationPlan(BaseModel):
    """Pure planning result; creating it does not mutate source records."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    generated_at: datetime
    algorithm_version: str = ALGORITHM_VERSION

    status: Literal["READY", "BLOCKED"]
    blocked_reasons: list[str] = Field(default_factory=list)

    decisions: list[AllocationDecision] = Field(default_factory=list)
    unallocated_needs: list[UnallocatedNeed] = Field(default_factory=list)

    inventory_state_version: str
    notes: list[str] = Field(default_factory=list)


# Explicit mappings only. Unsupported combinations are not guessed.
_NEED_RESOURCE_TYPES: dict[NeedType, set[ResourceType]] = {
    NeedType.RESCUE: {
        ResourceType.RESCUE_EQUIPMENT,
        ResourceType.LIFE_JACKETS,
        ResourceType.BOATS,
    },
    NeedType.EVACUATION: {
        ResourceType.BOATS,
        ResourceType.VEHICLES,
        ResourceType.LIFE_JACKETS,
    },
    NeedType.FOOD: {ResourceType.FOOD},
    NeedType.DRINKING_WATER: {ResourceType.DRINKING_WATER},
    NeedType.MEDICAL: {ResourceType.MEDICAL_KITS},
    NeedType.SHELTER: {ResourceType.SHELTER_KITS},
    NeedType.TRANSPORT: {ResourceType.VEHICLES},
    NeedType.SANITATION: {ResourceType.SANITATION_KITS},
    NeedType.OTHER: {ResourceType.OTHER},
}

_NEED_TEAM_CAPABILITIES: dict[NeedType, set[TeamCapability]] = {
    NeedType.RESCUE: {
        TeamCapability.WATER_RESCUE,
        TeamCapability.BOAT_OPERATIONS,
        TeamCapability.SEARCH_AND_RESCUE,
    },
    NeedType.EVACUATION: {
        TeamCapability.EVACUATION,
        TeamCapability.TRANSPORT,
        TeamCapability.BOAT_OPERATIONS,
    },
    NeedType.FOOD: {TeamCapability.FOOD_DISTRIBUTION},
    NeedType.DRINKING_WATER: {TeamCapability.WATER_DISTRIBUTION},
    NeedType.MEDICAL: {TeamCapability.MEDICAL_AID},
    NeedType.SHELTER: {TeamCapability.SHELTER_SUPPORT},
    NeedType.TRANSPORT: {TeamCapability.TRANSPORT},
    NeedType.SANITATION: {TeamCapability.GENERAL_SUPPORT},
    NeedType.OTHER: {TeamCapability.GENERAL_SUPPORT},
}

_URGENCY_RANK = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MODERATE": 2,
    "LOW": 3,
    "UNKNOWN": 4,
}

_ELIGIBLE_NEED_STATUSES = {
    NeedStatus.CONFIRMED,
    NeedStatus.PARTIALLY_FULFILLED,
}


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _age_is_acceptable(
    timestamp: datetime | None,
    now: datetime,
    maximum_age: timedelta,
) -> bool:
    if timestamp is None or not _is_aware(timestamp):
        return False

    age = now - timestamp.astimezone(timezone.utc)
    return timedelta(0) <= age <= maximum_age


def _normalise_unit(unit: str) -> str:
    # Deliberately exact after whitespace/case normalisation.
    # We do not assume that different units are interchangeable.
    return " ".join(unit.strip().casefold().split())


def inventory_ineligibility_reasons(
    item: ResourceInventory,
    now: datetime,
    maximum_age: timedelta = DEFAULT_INVENTORY_MAX_AGE,
) -> list[str]:
    """Why an inventory record cannot be proposed for any need right now."""
    reasons: list[str] = []

    if item.status != InventoryStatus.AVAILABLE:
        reasons.append(f"Status is {item.status}, not AVAILABLE.")
    if not item.availability_confirmed:
        reasons.append("Availability has not been confirmed.")
    if not _age_is_acceptable(item.last_verified_at, now, maximum_age):
        reasons.append("Last verification is missing, in the future, or too old.")
    if item.quantity_total - item.quantity_reserved - item.quantity_deployed <= 0:
        reasons.append("No unreserved stock remains.")

    return reasons


def team_ineligibility_reasons(
    team: ResponseTeam,
    now: datetime,
    maximum_age: timedelta = DEFAULT_TEAM_STATUS_MAX_AGE,
) -> list[str]:
    """Why a response team cannot be proposed for any need right now."""
    reasons: list[str] = []

    if team.status != TeamStatus.AVAILABLE:
        reasons.append(f"Status is {team.status}, not AVAILABLE.")
    if not team.availability_confirmed:
        reasons.append("Availability has not been confirmed.")
    if team.personnel_count <= 0:
        reasons.append("No personnel recorded.")
    if team.current_assignment_id is not None:
        reasons.append("Already has an assignment.")
    if not _age_is_acceptable(team.last_status_update, now, maximum_age):
        reasons.append("Last status update is in the future or too old.")

    return reasons


def _decision_id(need_id: str, inventory_id: str, team_id: str) -> str:
    return f"proposal:{need_id}:{inventory_id}:{team_id}"


def generate_allocation_plan(
    *,
    event: FloodEvent,
    locations: list[AffectedLocation],
    needs: list[ResourceNeed],
    inventory: list[ResourceInventory],
    teams: list[ResponseTeam],
    generated_at: datetime | None = None,
    inventory_state_version: str,
    inventory_max_age: timedelta = DEFAULT_INVENTORY_MAX_AGE,
    team_status_max_age: timedelta = DEFAULT_TEAM_STATUS_MAX_AGE,
) -> AllocationPlan:
    """
    Generate deterministic allocation proposals from an explicit snapshot.

    This function performs no database access, persistence, approval,
    reservation, or dispatch. Callers must supply the snapshot version.
    """

    now = generated_at or datetime.now(timezone.utc)

    if not _is_aware(now):
        raise ValueError("generated_at must include timezone information.")

    if inventory_max_age < timedelta(0):
        raise ValueError("inventory_max_age cannot be negative.")

    if team_status_max_age < timedelta(0):
        raise ValueError("team_status_max_age cannot be negative.")

    now = now.astimezone(timezone.utc)

    blocked_reasons: list[str] = []

    if event.status != EventStatus.ACTIVE:
        blocked_reasons.append("Flood event is not ACTIVE.")

    if event.verification_status != EventVerificationStatus.VERIFIED:
        blocked_reasons.append("Flood event is not VERIFIED.")

    if blocked_reasons:
        return AllocationPlan(
            event_id=event.event_id,
            generated_at=now,
            status="BLOCKED",
            blocked_reasons=blocked_reasons,
            inventory_state_version=inventory_state_version,
            notes=["No allocation proposals were generated."],
        )

    location_by_id: dict[str, AffectedLocation] = {}
    for location in locations:
        if location.event_id == event.event_id:
            location_by_id[location.location_id] = location

    # Track provisional use locally so the same stock or team is not
    # proposed more than once beyond its available capacity.
    remaining_stock: dict[str, float] = {}
    for item in inventory:
        remaining_stock[item.inventory_id] = (
            item.quantity_total
            - item.quantity_reserved
            - item.quantity_deployed
        )

    used_team_ids: set[str] = set()
    decisions: list[AllocationDecision] = []
    unallocated: list[UnallocatedNeed] = []

    ordered_needs = sorted(
        needs,
        key=lambda need: (
            _URGENCY_RANK.get(str(need.urgency), 4),
            need.reported_at.astimezone(timezone.utc)
            if _is_aware(need.reported_at)
            else datetime.max.replace(tzinfo=timezone.utc),
            need.need_id,
        ),
    )

    eligible_inventory = [
        item
        for item in inventory
        if not inventory_ineligibility_reasons(item, now, inventory_max_age)
    ]
    eligible_inventory.sort(key=lambda item: item.inventory_id)

    eligible_teams = [
        team
        for team in teams
        if not team_ineligibility_reasons(team, now, team_status_max_age)
    ]
    eligible_teams.sort(key=lambda team: team.team_id)

    for need in ordered_needs:
        reasons: list[str] = []

        if need.event_id != event.event_id:
            continue

        if need.status not in _ELIGIBLE_NEED_STATUSES:
            reasons.append(
                f"Need status {need.status} is not eligible for allocation."
            )

        location = location_by_id.get(need.location_id)
        if location is None:
            reasons.append(
                "No affected-location record for this event matches the need."
            )

        if need.quantity_requested is None:
            reasons.append("Requested quantity is unknown.")
        elif not need.quantity_unit or not need.quantity_unit.strip():
            reasons.append("Requested quantity unit is unknown.")
        elif need.quantity_fulfilled >= need.quantity_requested:
            reasons.append("No unfulfilled requested quantity remains.")

        if reasons:
            unallocated.append(
                UnallocatedNeed(need_id=need.need_id, reasons=reasons)
            )
            continue

        assert location is not None
        assert need.quantity_requested is not None
        assert need.quantity_unit is not None

        quantity_remaining = (
            need.quantity_requested - need.quantity_fulfilled
        )

        matching_stock = [
            item
            for item in eligible_inventory
            if remaining_stock[item.inventory_id] > 0
            and item.resource_type in _NEED_RESOURCE_TYPES[need.need_type]
            and _normalise_unit(item.quantity_unit)
            == _normalise_unit(need.quantity_unit)
        ]

        matching_teams = [
            team
            for team in eligible_teams
            if team.team_id not in used_team_ids
            and team.capabilities
            and bool(
                set(team.capabilities)
                & _NEED_TEAM_CAPABILITIES[need.need_type]
            )
        ]

        if not matching_stock:
            reasons.append(
                "No sufficiently verified, fresh, available compatible "
                "inventory with an exactly matching unit was found."
            )

        if not matching_teams:
            reasons.append(
                "No sufficiently fresh, confirmed available team with "
                "a compatible capability was found."
            )

        if reasons:
            unallocated.append(
                UnallocatedNeed(need_id=need.need_id, reasons=reasons)
            )
            continue

        # Deterministic greedy policy: most urgent need first, then
        # inventory ID and team ID. This is not a global optimum.
        selected_stock = matching_stock[0]
        selected_team = matching_teams[0]

        proposed_quantity = min(
            quantity_remaining,
            remaining_stock[selected_stock.inventory_id],
        )

        if proposed_quantity <= 0:
            unallocated.append(
                UnallocatedNeed(
                    need_id=need.need_id,
                    reasons=["No positive compatible stock remains."],
                )
            )
            continue

        constraints = [
            "Proposal only; human review and approval are required.",
            "No reservation, dispatch, or database mutation was performed.",
        ]
        uncertainties: list[str] = []

        if location.reassessment_required:
            uncertainties.append(
                "Affected location is marked for reassessment."
            )

        if location.severity.value == "UNKNOWN":
            uncertainties.append(
                "Location severity is UNKNOWN; this plan does not infer safety."
            )

        if need.urgency.value == "UNKNOWN":
            uncertainties.append(
                "Need urgency is UNKNOWN and was not treated as critical."
            )

        if proposed_quantity < quantity_remaining:
            constraints.append(
                "Available compatible stock covers only part of the "
                "remaining requested quantity."
            )

        decisions.append(
            AllocationDecision(
                decision_id=_decision_id(
                    need.need_id,
                    selected_stock.inventory_id,
                    selected_team.team_id,
                ),
                need_id=need.need_id,
                location_id=location.location_id,
                inventory_id=selected_stock.inventory_id,
                team_id=selected_team.team_id,
                proposed_quantity=proposed_quantity,
                quantity_unit=need.quantity_unit,
                rationale=[
                    f"Need status is {need.status}.",
                    f"Need urgency is {need.urgency}.",
                    f"Resource type {selected_stock.resource_type} is "
                    f"explicitly compatible with need type {need.need_type}.",
                    "Inventory availability is confirmed and its "
                    "verification timestamp meets the configured freshness limit.",
                    "Team availability is confirmed and its status "
                    "timestamp meets the configured freshness limit.",
                    "Resource unit matches the requested unit after "
                    "case and whitespace normalisation.",
                    "Allocation order is deterministic, not a global optimisation.",
                ],
                constraints=constraints,
                unresolved_uncertainties=uncertainties,
            )
        )

        remaining_stock[selected_stock.inventory_id] -= proposed_quantity
        used_team_ids.add(selected_team.team_id)

        # Do not allow this same need to receive a second team in this
        # planning run. Partial coverage is surfaced for human review.
        if proposed_quantity < quantity_remaining:
            unallocated.append(
                UnallocatedNeed(
                    need_id=need.need_id,
                    reasons=[
                        "Need is only partially covered by the selected "
                        "inventory; additional stock or a separate planning "
                        "decision is required."
                    ],
                )
            )

    return AllocationPlan(
        event_id=event.event_id,
        generated_at=now,
        status="READY",
        decisions=decisions,
        unallocated_needs=unallocated,
        inventory_state_version=inventory_state_version,
        notes=[
            "READY means planning completed, not that every need was fulfilled.",
            "Only the supplied snapshot was evaluated.",
            "No live data sources were queried.",
            "Recommendations are not approved assignments or dispatches.",
        ],
    )
