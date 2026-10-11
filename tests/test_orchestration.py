"""Tests for need estimation, NGO selection and run_orchestration."""

from datetime import datetime, timezone

import pytest

from app.models.affected_location import AffectedLocation, SeverityLevel
from app.services.orchestration.need_estimation import estimate_needs
from app.services.orchestration.run import OrchestrationError, run_orchestration
from tests.test_plan_lifecycle import lifecycle


def test_need_estimation_lists_missing_inputs_and_never_guesses():
    known = AffectedLocation(location_id="a", event_id="e", location_name="A", state="S",
                             severity=SeverityLevel.HIGH, population_affected=1000)
    unknown = AffectedLocation(location_id="b", event_id="e", location_name="B", state="S")
    estimate = estimate_needs([known, unknown])
    assert estimate.missing_inputs == ["b: severity, population_affected"]
    water = next(n for n in estimate.needs if n.need_type == "DRINKING_WATER")
    assert water.location_id == "a" and water.quantity == 15000


@pytest.mark.asyncio
async def test_run_orchestration_selects_in_range_ngo_and_is_idempotent(seeded_db):
    service = lifecycle(seeded_db).plan_service
    first = await run_orchestration(seeded_db, service, "sample-event-001")
    assert first.ngo_id == "sample-org-001" and not first.reused
    assert "sample-org-003" in first.selection.excluded
    plan = await seeded_db["allocation_plans"].find_one({"_id": first.plan_id})
    assert plan["plan"]["status"] == "READY" and plan["ngo_id"] == "sample-org-001"
    second = await run_orchestration(seeded_db, service, "sample-event-001")
    assert second.reused and second.plan_id == first.plan_id


@pytest.mark.asyncio
async def test_run_orchestration_gates_unverified_event(seeded_db):
    with pytest.raises(OrchestrationError) as err:
        await run_orchestration(seeded_db, lifecycle(seeded_db).plan_service, "sample-event-002")
    assert err.value.code == "ORCHESTRATION_BLOCKED"
