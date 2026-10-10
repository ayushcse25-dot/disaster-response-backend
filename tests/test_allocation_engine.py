from datetime import datetime, timedelta, timezone

from app.models.affected_location import AffectedLocation, SeverityLevel
from app.models.enums import EventStatus, EventVerificationStatus
from app.models.flood_event import FloodEvent
from app.models.resource_inventory import (
    InventoryStatus,
    ResourceInventory,
    ResourceType,
)
from app.models.resource_need import NeedStatus, NeedType, NeedUrgency, ResourceNeed
from app.models.response_team import (
    ResponseTeam,
    TeamCapability,
    TeamStatus,
)
from app.services.allocation_engine import generate_allocation_plan


NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


def make_event(**overrides):
    data = {
        "event_id": "event-001",
        "title": "Patna Flood",
        "description": "Flood response planning test.",
        "location_name": "Patna",
        "state": "Bihar",
        "district": "Patna",
        "status": EventStatus.ACTIVE,
        "verification_status": EventVerificationStatus.VERIFIED,
    }
    data.update(overrides)
    return FloodEvent(**data)


def make_location(**overrides):
    data = {
        "location_id": "location-001",
        "event_id": "event-001",
        "location_name": "Affected Area",
        "state": "Bihar",
        "district": "Patna",
        "severity": SeverityLevel.HIGH,
        "reassessment_required": False,
    }
    data.update(overrides)
    return AffectedLocation(**data)


def make_need(**overrides):
    data = {
        "need_id": "need-001",
        "event_id": "event-001",
        "location_id": "location-001",
        "need_type": NeedType.FOOD,
        "description": "Food packets required.",
        "urgency": NeedUrgency.HIGH,
        "status": NeedStatus.CONFIRMED,
        "quantity_requested": 20,
        "quantity_fulfilled": 0,
        "quantity_unit": "packets",
        "reported_at": NOW,
        "updated_at": NOW,
    }
    data.update(overrides)
    return ResourceNeed(**data)


def make_inventory(**overrides):
    data = {
        "inventory_id": "inventory-001",
        "organisation_id": "organisation-001",
        "resource_type": ResourceType.FOOD,
        "resource_name": "Food packets",
        "quantity_total": 100,
        "quantity_reserved": 0,
        "quantity_deployed": 0,
        "quantity_unit": "packets",
        "storage_location": "Patna warehouse",
        "status": InventoryStatus.AVAILABLE,
        "availability_confirmed": True,
        "last_verified_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
    }
    data.update(overrides)
    return ResourceInventory(**data)


def make_team(**overrides):
    data = {
        "team_id": "team-001",
        "organisation_id": "organisation-001",
        "team_name": "Food Distribution Team",
        "capabilities": [TeamCapability.FOOD_DISTRIBUTION],
        "equipment": [],
        "personnel_count": 4,
        "status": TeamStatus.AVAILABLE,
        "current_assignment_id": None,
        "last_status_update": NOW,
        "availability_confirmed": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    data.update(overrides)
    return ResponseTeam(**data)


def plan(event=None, locations=None, needs=None, inventory=None, teams=None):
    return generate_allocation_plan(
        event=event or make_event(),
        locations=locations if locations is not None else [make_location()],
        needs=needs if needs is not None else [make_need()],
        inventory=inventory if inventory is not None else [make_inventory()],
        teams=teams if teams is not None else [make_team()],
        generated_at=NOW,
        inventory_state_version="snapshot-test-001",
    )


def test_verified_active_event_generates_proposal():
    result = plan()

    assert result.status == "READY"
    assert len(result.decisions) == 1

    decision = result.decisions[0]
    assert decision.need_id == "need-001"
    assert decision.inventory_id == "inventory-001"
    assert decision.team_id == "team-001"
    assert decision.proposed_quantity == 20
    assert decision.status == "PROPOSED"


def test_unverified_event_blocks_allocation():
    event = make_event(
        verification_status=EventVerificationStatus.UNVERIFIED
    )

    result = plan(event=event)

    assert result.status == "BLOCKED"
    assert result.decisions == []
    assert any("VERIFIED" in reason for reason in result.blocked_reasons)


def test_non_active_event_blocks_allocation():
    event = make_event(status=EventStatus.RESOLVED)

    result = plan(event=event)

    assert result.status == "BLOCKED"
    assert result.decisions == []


def test_stale_inventory_is_not_allocated():
    inventory = make_inventory(
        last_verified_at=NOW - timedelta(hours=25)
    )

    result = plan(inventory=[inventory])

    assert result.decisions == []
    assert len(result.unallocated_needs) == 1


def test_unconfirmed_inventory_is_not_allocated():
    inventory = make_inventory(availability_confirmed=False)

    result = plan(inventory=[inventory])

    assert result.decisions == []
    assert len(result.unallocated_needs) == 1


def test_stale_team_status_is_not_allocated():
    team = make_team(
        last_status_update=NOW - timedelta(hours=3)
    )

    result = plan(teams=[team])

    assert result.decisions == []
    assert len(result.unallocated_needs) == 1


def test_team_with_existing_assignment_is_not_allocated():
    team = make_team(current_assignment_id="assignment-existing")

    result = plan(teams=[team])

    assert result.decisions == []
    assert len(result.unallocated_needs) == 1


def test_incompatible_team_capability_is_not_allocated():
    team = make_team(
        capabilities=[TeamCapability.MEDICAL_AID]
    )

    result = plan(teams=[team])

    assert result.decisions == []
    assert len(result.unallocated_needs) == 1


def test_inventory_stock_is_not_overallocated():
    inventory = make_inventory(quantity_total=15)
    first_need = make_need(
        need_id="need-001",
        quantity_requested=10,
    )
    second_need = make_need(
        need_id="need-002",
        quantity_requested=10,
    )
    first_team = make_team(team_id="team-001")
    second_team = make_team(team_id="team-002")

    result = plan(
        needs=[first_need, second_need],
        inventory=[inventory],
        teams=[first_team, second_team],
    )

    assert len(result.decisions) == 2
    assert sum(
        decision.proposed_quantity for decision in result.decisions
    ) == 15

    quantities = {
        decision.need_id: decision.proposed_quantity
        for decision in result.decisions
    }
    assert quantities["need-001"] == 10
    assert quantities["need-002"] == 5

    assert any(
        item.need_id == "need-002"
        for item in result.unallocated_needs
    )


def test_need_for_another_event_is_ignored():
    other_event_need = make_need(event_id="another-event")

    result = plan(needs=[other_event_need])

    assert result.decisions == []
    assert result.unallocated_needs == []


def test_rejected_need_is_not_allocated():
    need = make_need(status=NeedStatus.REJECTED)

    result = plan(needs=[need])

    assert result.decisions == []
    assert len(result.unallocated_needs) == 1


def test_unknown_inventory_verification_is_not_allocated():
    inventory = make_inventory(last_verified_at=None)

    result = plan(inventory=[inventory])

    assert result.decisions == []
    assert len(result.unallocated_needs) == 1


def test_plan_does_not_mutate_inventory_or_team():
    inventory = make_inventory()
    team = make_team()

    original_reserved = inventory.quantity_reserved
    original_deployed = inventory.quantity_deployed
    original_assignment = team.current_assignment_id

    result = plan(inventory=[inventory], teams=[team])

    assert len(result.decisions) == 1
    assert inventory.quantity_reserved == original_reserved
    assert inventory.quantity_deployed == original_deployed
    assert team.current_assignment_id == original_assignment


def test_plan_records_snapshot_version_and_algorithm_version():
    result = plan()

    assert result.inventory_state_version == "snapshot-test-001"
    assert result.algorithm_version == "1.0.0"


def test_incompatible_inventory_unit_is_not_allocated():
    inventory = make_inventory(quantity_unit="litres")

    result = plan(inventory=[inventory])

    assert result.decisions == []
    assert len(result.unallocated_needs) == 1
