"""Scripted demo that drives the real pipeline one step at a time.

Steps (on sample-event-001):
  1 WARNING_RECEIVED   a sample gauge warning is recorded
  2 PLAN_GENERATED     run_orchestration selects an NGO and stores a READY plan
  3 TASKS_CREATED      requires a human to approve that plan; tasks go to worker W-001
  4 DISRUPTION         the worker reports a problem (or, with no worker, stock turns stale)
  5 REPLANNED          the plan is replanned as the next version

The director never approves anything. Only sample records are touched.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.models.enums import EventVerificationStatus, ObservationType
from app.models.flood_observation import FloodObservation
from app.models.user import Principal, Role
from app.services import task_service
from app.services.allocation_plan_service import AllocationPlanService
from app.services.orchestration.run import run_orchestration
from app.services.plan_lifecycle_service import PlanLifecycleService, replan_reasons

DEMO_EVENT = "sample-event-001"
DEMO_WORKER = "W-001"
STATE = "demo_state"
DIRECTOR = Principal(user_id="system:demo-director", role=Role.AUTHORITY, display_name="Demo director")
STEPS = ["RESET", "WARNING_RECEIVED", "PLAN_GENERATED", "TASKS_CREATED", "DISRUPTION", "REPLANNED"]


class DemoError(Exception):
    def __init__(self, status_code: int, code: str, detail: Any) -> None:
        super().__init__(str(detail))
        self.status_code = status_code
        self.code = code
        self.detail = detail


async def get_state(database: Any) -> dict[str, Any]:
    state = await database[STATE].find_one({"_id": "current"})
    if state is None:
        return {"step": 0, "step_name": "NOT_STARTED", "plan_id": None, "timeline": [],
                "next_step": STEPS[1]}
    state.pop("_id")
    state["next_step"] = STEPS[state["step"] + 1] if state["step"] + 1 < len(STEPS) else None
    return state


async def _record(database: Any, step: int, title: str, detail: Any, **fields: Any) -> dict[str, Any]:
    entry = {"at": datetime.now(timezone.utc).isoformat(), "step": step,
             "step_name": STEPS[step], "title": title, "detail": detail}
    await database[STATE].update_one(
        {"_id": "current"},
        {"$set": {"step": step, "step_name": STEPS[step], "is_sample": True, **fields},
         "$push": {"timeline": entry}},
        upsert=True,
    )
    return await get_state(database)


async def reset(database: Any) -> dict[str, Any]:
    """Remove everything the demo or earlier runs derived from sample data, then reseed."""
    from scripts.seed_sample import seed

    for collection in ("allocation_plans", "deployment_assignments", "ngo_assignments",
                       "flood_observations", STATE):
        await database[collection].delete_many({"is_sample": True})
    await database["decision_audits"].delete_many({"event_id": {"$regex": "^sample-"}})
    counts = await seed(database)
    await database[STATE].delete_many({})
    return await _record(database, 0, "Sample data restored", counts, plan_id=None)


async def step(database: Any, plan_service: AllocationPlanService) -> dict[str, Any]:
    state = await get_state(database)
    current = state["step"]
    lifecycle = PlanLifecycleService(database, plan_service)

    if current == 0:
        now = datetime.now(timezone.utc)
        observation = FloodObservation(
            observation_id=f"sample-obs-demo-{uuid4().hex[:8]}", event_id=DEMO_EVENT,
            source_id="sample-source-gauge", observation_type=ObservationType.WEATHER_WARNING,
            title="SAMPLE — Heavy rainfall warning, river expected to rise further",
            description="SAMPLE DATA — NOT LIVE FLOOD INFORMATION.", location_name="Patna",
            state="Bihar", observed_at=now - timedelta(minutes=2), received_at=now,
            verification_status=EventVerificationStatus.VERIFIED, is_sample=True,
        )
        document = observation.model_dump(mode="json")
        document["_id"] = document.pop("observation_id")
        await database["flood_observations"].insert_one(document)
        return await _record(database, 1, "Warning received", {"observation_id": document["_id"]})

    if current == 1:
        result = await run_orchestration(database, plan_service, DEMO_EVENT)
        return await _record(
            database, 2, f"NGO {result.ngo_id} selected; plan v{result.plan_version} generated",
            {"plan_id": result.plan_id, "explanation": result.selection.explanation,
             "next": "A human must approve this plan: POST /api/v1/allocation-plans/{plan_id}/approve"},
            plan_id=result.plan_id,
        )

    plan = await database["allocation_plans"].find_one({"_id": state["plan_id"]})
    if current == 2:
        if plan is None or plan.get("approval_status") != "APPROVED":
            raise DemoError(409, "WAITING_FOR_APPROVAL",
                            f"Approve plan {state['plan_id']} first; the demo never approves plans.")
        tasks = await task_service.list_tasks(database, DIRECTOR, plan_id=state["plan_id"])
        assigned = []
        worker = await database["users"].find_one(
            {"ngo_id": plan.get("ngo_id"), "worker_id": DEMO_WORKER, "status": "ACTIVE"})
        if worker is not None:
            for task in tasks:
                await task_service.transition(database, DIRECTOR, task.assignment_id, "assign",
                                              worker_id=DEMO_WORKER, note="Assigned by demo script.")
                assigned.append(task.assignment_id)
        return await _record(database, 3, f"{len(tasks)} task(s) created on approval",
                             {"task_ids": [t.assignment_id for t in tasks],
                              "assigned_to": DEMO_WORKER if assigned else None})

    if current == 3:
        tasks = await task_service.list_tasks(database, DIRECTOR, plan_id=state["plan_id"])
        assigned = [t for t in tasks if t.status == "ASSIGNED" and t.worker_user_id]
        if assigned:
            task = assigned[0]
            worker = Principal(user_id=task.worker_user_id, role=Role.WORKER,
                               display_name=DEMO_WORKER, ngo_id=task.ngo_id, worker_id=task.worker_id)
            await task_service.transition(database, worker, task.assignment_id, "acknowledge")
            await task_service.transition(database, worker, task.assignment_id, "problem",
                                          note="SAMPLE: access road submerged, boat cannot launch here.")
            detail = {"task_id": task.assignment_id, "kind": "WORKER_PROBLEM"}
        else:
            stale = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
            inventory_ids = [d["inventory_id"] for d in plan["plan"]["decisions"]]
            await database["resource_inventory"].update_many(
                {"_id": {"$in": inventory_ids}, "is_sample": True}, {"$set": {"last_verified_at": stale}})
            detail = {"inventory_ids": inventory_ids, "kind": "RESOURCE_STALE"}
        record = await plan_service.plan_repository.get_by_id(state["plan_id"])
        detail["replan_reasons"] = await replan_reasons(database, record)
        return await _record(database, 4, "Disruption: replan suggested", detail)

    if current == 4:
        version = int(plan.get("version") or 1)
        new = await lifecycle.replan(state["plan_id"], expected_version=version, actor_id=DIRECTOR.user_id)
        return await _record(database, 5, f"Replanned as version {new.version}",
                             {"plan_id": new.plan_id, "supersedes": state["plan_id"],
                              "decisions": len(new.plan.decisions)},
                             plan_id=new.plan_id)

    raise DemoError(409, "DEMO_COMPLETE", "All steps are done; POST /api/v1/demo/reset to start again.")
