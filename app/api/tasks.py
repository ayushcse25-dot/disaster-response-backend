"""Field task (work order) endpoints for NGO staff and workers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.api.auth_deps import CurrentUser
from app.api.deps import get_database
from app.core.errors import ApiError
from app.models.deployment_assignment import DeploymentAssignment
from app.services import task_service
from app.services.task_service import TaskError

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])
Database = Annotated[AsyncDatabase, Depends(get_database)]


class TaskAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=2000)


class AssignRequest(TaskAction):
    worker_id: str = Field(min_length=1, max_length=30)


class SubmitRequest(TaskAction):
    photo_refs: list[str] = Field(default_factory=list, max_length=20)


@router.get("", response_model=list[DeploymentAssignment])
async def list_tasks(
    user: CurrentUser, database: Database,
    plan_id: Annotated[str | None, Query(max_length=100)] = None,
    status: Annotated[str | None, Query(max_length=30)] = None,
) -> list[DeploymentAssignment]:
    """Workers see their own tasks, NGO staff their organisation's, authority all."""
    return await task_service.list_tasks(database, user, plan_id=plan_id, status=status)


@router.get("/{task_id}", response_model=DeploymentAssignment)
async def get_task(task_id: str, user: CurrentUser, database: Database) -> DeploymentAssignment:
    try:
        return await task_service.get_task(database, user, task_id)
    except TaskError as exc:
        raise ApiError(exc.status_code, exc.code, exc.detail) from exc


async def _act(database, user, task_id: str, action: str, **kwargs) -> DeploymentAssignment:
    try:
        return await task_service.transition(database, user, task_id, action, **kwargs)
    except TaskError as exc:
        raise ApiError(exc.status_code, exc.code, exc.detail) from exc


@router.post("/{task_id}/assign", response_model=DeploymentAssignment)
async def assign(task_id: str, body: AssignRequest, user: CurrentUser,
                 database: Database) -> DeploymentAssignment:
    return await _act(database, user, task_id, "assign", worker_id=body.worker_id, note=body.note)


@router.post("/{task_id}/submit", response_model=DeploymentAssignment)
async def submit(task_id: str, body: SubmitRequest, user: CurrentUser,
                 database: Database) -> DeploymentAssignment:
    return await _act(database, user, task_id, "submit", note=body.note, photo_refs=body.photo_refs)


def _simple(action: str):
    async def endpoint(task_id: str, user: CurrentUser, database: Database,
                       body: TaskAction | None = None) -> DeploymentAssignment:
        return await _act(database, user, task_id, action, note=body.note if body else None)

    endpoint.__name__ = f"{action}_task"
    return endpoint


for _action in ("acknowledge", "start", "problem", "verify", "reject"):
    router.add_api_route(
        f"/{{task_id}}/{_action}", _simple(_action), methods=["POST"],
        response_model=DeploymentAssignment, name=f"{_action}_task",
    )
