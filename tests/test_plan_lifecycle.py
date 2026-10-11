"""Integration tests for plan versions, replanning and manual allocation."""

import pytest

from app.repositories.affected_location_repository import AffectedLocationRepository
from app.repositories.allocation_plan_repository import AllocationPlanRepository
from app.repositories.flood_event_repository import FloodEventRepository
from app.repositories.resource_inventory_repository import ResourceInventoryRepository
from app.repositories.resource_need_repository import ResourceNeedRepository
from app.repositories.response_team_repository import ResponseTeamRepository
from app.services.allocation_plan_service import AllocationPlanService
from app.services.plan_lifecycle_service import (
    ManualAllocationInvalid,
    ManualAllocationItem,
    PlanLifecycleService,
    PlanVersionConflict,
)


def lifecycle(db) -> PlanLifecycleService:
    return PlanLifecycleService(db, AllocationPlanService(
        plan_repository=AllocationPlanRepository(db),
        event_repository=FloodEventRepository(db),
        location_repository=AffectedLocationRepository(db),
        need_repository=ResourceNeedRepository(db),
        inventory_repository=ResourceInventoryRepository(db),
        team_repository=ResponseTeamRepository(db),
    ))


@pytest.mark.asyncio
async def test_replan_creates_next_version_and_rejects_stale_version(seeded_db):
    service = lifecycle(seeded_db)
    new = await service.replan("sample-plan-001", expected_version=1, actor_id="op")
    assert new.version == 2 and new.supersedes_plan_id == "sample-plan-001"
    old = await seeded_db["allocation_plans"].find_one({"_id": "sample-plan-001"})
    assert old["approval_status"] == "SUPERSEDED"
    with pytest.raises(PlanVersionConflict) as err:
        await service.replan(new.plan_id, expected_version=1, actor_id="op")
    assert err.value.code == "VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_manual_allocation_reports_per_item_reasons(seeded_db):
    service = lifecycle(seeded_db)
    with pytest.raises(ManualAllocationInvalid) as err:
        await service.manual_allocation(
            "sample-plan-001", expected_version=1, actor_id="op", reason="field call",
            items=[ManualAllocationItem(
                need_id="sample-need-003", inventory_id="sample-inv-003",
                team_id="sample-team-003", quantity=10,
            )],
        )
    [problem] = err.value.detail
    assert problem["index"] == 0 and any("Inventory:" in r for r in problem["reasons"])

    record = await service.manual_allocation(
        "sample-plan-001", expected_version=1, actor_id="op", reason="field call",
        items=[ManualAllocationItem(
            need_id="sample-need-001", inventory_id="sample-inv-001",
            team_id="sample-team-001", quantity=1,
        )],
    )
    assert record.source == "MANUAL" and record.version == 2


@pytest.mark.asyncio
async def test_read_time_replan_suggested_when_resource_turns_stale(seeded_db):
    service = lifecycle(seeded_db)
    record = await AllocationPlanRepository(seeded_db).get_by_id("sample-plan-001")
    assert (await service.view(record)).replan_suggested is False
    await seeded_db["resource_inventory"].update_one(
        {"_id": "sample-inv-001"}, {"$set": {"last_verified_at": "2020-01-01T00:00:00+00:00"}}
    )
    view = await service.view(record)
    assert view.replan_suggested and "sample-inv-001" in view.replan_reasons[0]
