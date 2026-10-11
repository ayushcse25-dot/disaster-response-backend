"""Demo director: disabled by default, never approves, walks the real pipeline."""

import pytest

from app.services import demo_director
from app.services.allocation_approval_service import AllocationApprovalService
from app.services.auth_service import create_worker
from app.services.demo_director import DemoError
from tests.test_plan_lifecycle import lifecycle


def test_demo_routes_refuse_when_disabled(client):
    response = client.get("/api/v1/demo/state")
    assert response.status_code == 404 and response.json()["code"] == "DEMO_DISABLED"


@pytest.mark.asyncio
async def test_demo_walkthrough_waits_for_human_approval(live_db):
    service = lifecycle(live_db).plan_service
    await demo_director.reset(live_db)
    await create_worker(live_db, "sample-org-001", "Demo worker", worker_id="W-001", is_sample=True)
    await demo_director.step(live_db, service)
    state = await demo_director.step(live_db, service)
    assert state["step_name"] == "PLAN_GENERATED"
    with pytest.raises(DemoError) as err:
        await demo_director.step(live_db, service)
    assert err.value.code == "WAITING_FOR_APPROVAL"

    await AllocationApprovalService(live_db).approve(
        state["plan_id"], actor_id="human", actor_type="AUTHORITY", reason="reviewed")
    await demo_director.step(live_db, service)
    disruption = await demo_director.step(live_db, service)
    assert disruption["timeline"][-1]["detail"]["replan_reasons"]
    final = await demo_director.step(live_db, service)
    assert final["step_name"] == "REPLANNED" and len(final["timeline"]) == 6
