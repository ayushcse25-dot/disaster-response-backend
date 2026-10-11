"""Field tasks (work orders) built on deployment_assignments.

Approval creates one assignment per plan decision with status APPROVED. From there:

    APPROVED -assign-> ASSIGNED -acknowledge-> ACKNOWLEDGED -start-> IN_PROGRESS
    ACKNOWLEDGED/IN_PROGRESS -problem-> PROBLEM -start-> IN_PROGRESS
    IN_PROGRESS/PROBLEM -submit-> SUBMITTED -verify-> NGO_VERIFIED
    SUBMITTED -reject-> FAILED

Every transition is a conditional update on the current status and appends to
history, so two concurrent actions cannot both apply.
"""

from datetime import datetime, timezone
from typing import Any

from app.models.deployment_assignment import AssignmentStatus as S
from app.models.deployment_assignment import DeploymentAssignment, TaskHistoryEntry
from app.models.user import Principal, Role

TASKS = "deployment_assignments"

# action -> (allowed from-statuses, to-status, roles allowed)
TRANSITIONS: dict[str, tuple[set[S], S, set[Role]]] = {
    "assign": ({S.APPROVED, S.ASSIGNED, S.ACKNOWLEDGED}, S.ASSIGNED, {Role.NGO_ADMIN, Role.AUTHORITY}),
    "acknowledge": ({S.ASSIGNED}, S.ACKNOWLEDGED, {Role.WORKER}),
    "start": ({S.ACKNOWLEDGED, S.PROBLEM}, S.IN_PROGRESS, {Role.WORKER}),
    "problem": ({S.ACKNOWLEDGED, S.IN_PROGRESS}, S.PROBLEM, {Role.WORKER}),
    "submit": ({S.IN_PROGRESS, S.PROBLEM}, S.SUBMITTED, {Role.WORKER}),
    "verify": ({S.SUBMITTED}, S.NGO_VERIFIED, {Role.NGO_ADMIN, Role.AUTHORITY}),
    "reject": ({S.SUBMITTED}, S.FAILED, {Role.NGO_ADMIN, Role.AUTHORITY}),
}


class TaskError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


def _task(document: dict[str, Any]) -> DeploymentAssignment:
    document = dict(document)
    document["assignment_id"] = document.pop("_id")
    return DeploymentAssignment.model_validate(document)


def _visible_filter(user: Principal) -> dict[str, Any]:
    if user.role == Role.WORKER:
        return {"worker_user_id": user.user_id}
    if user.role == Role.NGO_ADMIN:
        return {"ngo_id": user.ngo_id}
    return {}


async def list_tasks(
    database: Any, user: Principal, *, plan_id: str | None = None, status: str | None = None
) -> list[DeploymentAssignment]:
    query = _visible_filter(user)
    if plan_id:
        query["recommendation_id"] = plan_id
    if status:
        query["status"] = status
    documents = await database[TASKS].find(query).sort("created_at", 1).to_list(length=500)
    return [_task(d) for d in documents]


async def get_task(database: Any, user: Principal, task_id: str) -> DeploymentAssignment:
    document = await database[TASKS].find_one({"_id": task_id, **_visible_filter(user)})
    if document is None:
        # Same answer for "missing" and "not yours", so IDs cannot be probed.
        raise TaskError(404, "TASK_NOT_FOUND", "Task not found.")
    return _task(document)


async def transition(
    database: Any,
    user: Principal,
    task_id: str,
    action: str,
    *,
    note: str | None = None,
    worker_id: str | None = None,
    photo_refs: list[str] | None = None,
) -> DeploymentAssignment:
    allowed_from, to_status, roles = TRANSITIONS[action]
    if user.role not in roles:
        raise TaskError(403, "FORBIDDEN_ROLE", f"Role {user.role} cannot {action} a task.")
    task = await get_task(database, user, task_id)
    if task.status not in allowed_from:
        raise TaskError(409, "INVALID_TRANSITION", f"Cannot {action} a task in status {task.status}.")
    if action in ("problem", "reject") and not (note and note.strip()):
        raise TaskError(422, "NOTE_REQUIRED", f"A note is required to {action} a task.")

    now = datetime.now(timezone.utc)
    updates: dict[str, Any] = {"status": to_status.value, "updated_at": now.isoformat()}
    if action == "assign":
        if not worker_id:
            raise TaskError(422, "WORKER_REQUIRED", "worker_id is required.")
        worker = await database["users"].find_one({
            "ngo_id": task.ngo_id, "worker_id": worker_id, "role": Role.WORKER.value,
            "status": "ACTIVE",
        })
        if worker is None:
            raise TaskError(422, "WORKER_NOT_AVAILABLE",
                            "No active worker with that ID in this task's organisation.")
        updates.update(worker_user_id=worker["_id"], worker_id=worker_id)
        note = note or f"Assigned to {worker_id}."
    elif action == "acknowledge":
        updates["acknowledged_at"] = now.isoformat()
    elif action == "submit":
        updates["completion_note"] = note
        updates["photo_refs"] = list(task.photo_refs) + list(photo_refs or [])
    elif action == "verify":
        updates["completed_at"] = now.isoformat()

    entry = TaskHistoryEntry(
        actor_id=user.user_id, actor_role=user.role.value, action=action.upper(),
        from_status=task.status.value, to_status=to_status.value, note=note, at=now,
    )
    result = await database[TASKS].update_one(
        {"_id": task_id, "status": task.status.value},
        {"$set": updates, "$push": {"history": entry.model_dump(mode="json")}},
    )
    if result.matched_count != 1:
        raise TaskError(409, "INVALID_TRANSITION", "The task changed; reload and try again.")

    if action == "problem" and task.recommendation_id:
        await database["allocation_plans"].update_one(
            {"_id": task.recommendation_id},
            {"$addToSet": {"replan_flags": f"Task {task_id}: worker reported a problem: {note.strip()}"}},
        )
    return await get_task(database, user, task_id)
