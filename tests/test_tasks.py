"""Task workflow tests: approval creates work orders, workers act on their own tasks."""

import pytest

from app.models.user import Principal, Role
from app.services import auth_service, task_service
from app.services.allocation_approval_service import AllocationApprovalService
from app.services.task_service import TaskError

NGO = Principal(user_id="ngo1", role=Role.NGO_ADMIN, display_name="N", ngo_id="sample-org-001")
OTHER_NGO = Principal(user_id="ngo2", role=Role.NGO_ADMIN, display_name="M", ngo_id="sample-org-002")


async def approved_task(db):
    await AllocationApprovalService(db).approve(
        "sample-plan-001", actor_id="op", actor_type="AUTHORITY", reason="ok")
    [task, *_] = await task_service.list_tasks(db, NGO, plan_id="sample-plan-001")
    return task


@pytest.mark.asyncio
async def test_worker_lifecycle_and_problem_flags_plan(seeded_db):
    task = await approved_task(seeded_db)
    assert task.status == "APPROVED" and task.ngo_id == "sample-org-001"
    worker, _ = await auth_service.create_worker(seeded_db, "sample-org-001", "Ravi")
    await task_service.transition(seeded_db, NGO, task.assignment_id, "assign", worker_id=worker.worker_id)

    assert [t.assignment_id for t in await task_service.list_tasks(seeded_db, worker)] == [task.assignment_id]
    await task_service.transition(seeded_db, worker, task.assignment_id, "acknowledge")
    await task_service.transition(seeded_db, worker, task.assignment_id, "start")
    await task_service.transition(seeded_db, worker, task.assignment_id, "problem", note="Road flooded")
    plan = await seeded_db["allocation_plans"].find_one({"_id": "sample-plan-001"})
    assert "Road flooded" in plan["replan_flags"][0]

    await task_service.transition(seeded_db, worker, task.assignment_id, "submit",
                                  note="Delivered", photo_refs=["photo://1"])
    done = await task_service.transition(seeded_db, NGO, task.assignment_id, "verify")
    assert done.status == "NGO_VERIFIED"
    assert [h.action for h in done.history] == [
        "CREATE", "ASSIGN", "ACKNOWLEDGE", "START", "PROBLEM", "SUBMIT", "VERIFY"]


@pytest.mark.asyncio
async def test_other_ngo_and_invalid_transitions_are_refused(seeded_db):
    task = await approved_task(seeded_db)
    with pytest.raises(TaskError) as err:
        await task_service.transition(seeded_db, OTHER_NGO, task.assignment_id, "assign", worker_id="W-001")
    assert err.value.code == "TASK_NOT_FOUND"
    with pytest.raises(TaskError) as err:
        await task_service.transition(seeded_db, NGO, task.assignment_id, "verify")
    assert err.value.code == "INVALID_TRANSITION"
