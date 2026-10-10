"""Allocation-plan service tests."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from app.models.enums import EventStatus, EventVerificationStatus
from app.models.flood_event import FloodEvent
from app.services.allocation_plan_service import (
    AllocationPlanService,
    _planning_snapshot_digest,
)


def make_event(**overrides):
    data = {
        "event_id": "event-001",
        "title": "Patna Flood",
        "description": "Test event",
        "location_name": "Patna",
        "state": "Bihar",
        "district": "Patna",
        "status": EventStatus.ACTIVE,
        "verification_status": EventVerificationStatus.VERIFIED,
    }
    data.update(overrides)
    return FloodEvent(**data)


def make_service(event=None):
    plan_repo = AsyncMock()
    async def save(record):
        return record
    plan_repo.create.side_effect = save

    event_repo = AsyncMock()
    event_repo.get_by_id.return_value = event

    location_repo = AsyncMock()
    location_repo.list_for_planning.return_value = []
    need_repo = AsyncMock()
    need_repo.list_for_planning.return_value = []
    inventory_repo = AsyncMock()
    inventory_repo.list_for_planning.return_value = []
    team_repo = AsyncMock()
    team_repo.list_for_planning.return_value = []

    service = AllocationPlanService(
        plan_repository=plan_repo,
        event_repository=event_repo,
        location_repository=location_repo,
        need_repository=need_repo,
        inventory_repository=inventory_repo,
        team_repository=team_repo,
    )
    return service, plan_repo, inventory_repo


def test_generate_persists_proposal_only():
    service, plan_repo, _ = make_service(make_event())
    record = asyncio.run(service.generate_for_event("event-001"))

    assert record.event_id == "event-001"
    assert record.plan.status == "READY"
    assert record.plan.decisions == []
    assert record.plan.inventory_state_version.startswith("sha256:")
    plan_repo.create.assert_awaited_once()
    assert all(d.status == "PROPOSED" for d in record.plan.decisions)


def test_missing_event_does_not_persist():
    service, plan_repo, _ = make_service(None)
    with pytest.raises(LookupError):
        asyncio.run(service.generate_for_event("missing"))
    plan_repo.create.assert_not_awaited()


def test_snapshot_failure_does_not_persist():
    service, plan_repo, inventory_repo = make_service(make_event())
    inventory_repo.list_for_planning.side_effect = RuntimeError("snapshot limit")
    with pytest.raises(RuntimeError):
        asyncio.run(service.generate_for_event("event-001"))
    plan_repo.create.assert_not_awaited()


def test_list_plans_requires_existing_event():
    service, _, _ = make_service(None)
    with pytest.raises(LookupError):
        asyncio.run(service.list_plans("missing"))



def test_planning_snapshot_digest_covers_all_input_categories():
    event = {"event_id": "event-001", "status": "ACTIVE"}
    locations = [{"location_id": "location-1", "severity": "HIGH"}]
    needs = [{"need_id": "need-1", "quantity": 10}]
    inventory = [{"inventory_id": "stock-1", "quantity": 10}]
    teams = [{"team_id": "team-1", "personnel_count": 4}]

    baseline = _planning_snapshot_digest(
        event=event,
        locations=locations,
        needs=needs,
        inventory=inventory,
        teams=teams,
    )

    changed_snapshots = [
        {"event": {**event, "status": "INACTIVE"}, "locations": locations,
         "needs": needs, "inventory": inventory, "teams": teams},
        {"event": event, "locations": [{**locations[0], "severity": "CRITICAL"}],
         "needs": needs, "inventory": inventory, "teams": teams},
        {"event": event, "locations": locations,
         "needs": [{**needs[0], "quantity": 11}], "inventory": inventory,
         "teams": teams},
        {"event": event, "locations": locations, "needs": needs,
         "inventory": [{**inventory[0], "quantity": 9}], "teams": teams},
        {"event": event, "locations": locations, "needs": needs,
         "inventory": inventory,
         "teams": [{**teams[0], "personnel_count": 3}]},
    ]

    for snapshot in changed_snapshots:
        assert _planning_snapshot_digest(**snapshot) != baseline


def test_planning_snapshot_digest_is_order_independent():
    event = {"event_id": "event-001"}
    locations = [{"location_id": "location-1"}, {"location_id": "location-2"}]
    needs = [{"need_id": "need-1"}, {"need_id": "need-2"}]
    inventory = [{"inventory_id": "stock-1"}, {"inventory_id": "stock-2"}]
    teams = [{"team_id": "team-1"}, {"team_id": "team-2"}]

    first = _planning_snapshot_digest(
        event=event, locations=locations, needs=needs,
        inventory=inventory, teams=teams,
    )
    second = _planning_snapshot_digest(
        event=event, locations=list(reversed(locations)),
        needs=list(reversed(needs)), inventory=list(reversed(inventory)),
        teams=list(reversed(teams)),
    )

    assert first == second
