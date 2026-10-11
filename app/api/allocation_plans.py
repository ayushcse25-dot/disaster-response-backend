"""Endpoints for allocation proposals and human approval decisions."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_database
from app.exceptions import PlanningSnapshotError
from app.models.allocation_plan import AllocationPlanRecord
from app.repositories.affected_location_repository import AffectedLocationRepository
from app.repositories.allocation_plan_repository import AllocationPlanRepository
from app.repositories.flood_event_repository import FloodEventRepository
from app.repositories.resource_inventory_repository import ResourceInventoryRepository
from app.repositories.resource_need_repository import ResourceNeedRepository
from app.repositories.response_team_repository import ResponseTeamRepository
from app.services.allocation_plan_service import AllocationPlanService
from app.services.allocation_approval_service import (
    AllocationApprovalService,
    ApprovalConflict,
    ApprovalNotFound,
    ApprovalServiceUnavailable,
    ApprovalValidationError,
)

router = APIRouter(prefix="/api/v1", tags=["Allocation Plans"])


class DecisionRequest(BaseModel):
    """Decision metadata; these fields do not authenticate the caller."""
    model_config = ConfigDict(extra="forbid")
    actor_id: str = Field(min_length=1, max_length=100)
    actor_type: str = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=1, max_length=3000)


def get_allocation_plan_service(
    database: Annotated[AsyncDatabase, Depends(get_database)],
) -> AllocationPlanService:
    return AllocationPlanService(
        plan_repository=AllocationPlanRepository(database),
        event_repository=FloodEventRepository(database),
        location_repository=AffectedLocationRepository(database),
        need_repository=ResourceNeedRepository(database),
        inventory_repository=ResourceInventoryRepository(database),
        team_repository=ResponseTeamRepository(database),
    )


def get_allocation_approval_service(
    database: Annotated[AsyncDatabase, Depends(get_database)],
) -> AllocationApprovalService:
    return AllocationApprovalService(database)


def _raise_approval_http_error(exc: Exception) -> None:
    if isinstance(exc, ApprovalNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ApprovalConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ApprovalValidationError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, ApprovalServiceUnavailable):
        raise HTTPException(
            status_code=503,
            detail="The decision could not be persisted; do not treat it as committed.",
        ) from exc
    raise exc


@router.post(
    "/flood-events/{event_id}/allocation-plans",
    response_model=AllocationPlanRecord,
    status_code=status.HTTP_201_CREATED,
)
async def generate_allocation_plan(
    event_id: str,
    service: Annotated[AllocationPlanService, Depends(get_allocation_plan_service)],
) -> AllocationPlanRecord:
    """Generate and persist a proposal; never approve or dispatch it."""
    try:
        return await service.generate_for_event(event_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PlanningSnapshotError as exc:
        raise HTTPException(
            status_code=503,
            detail="The planning snapshot could not be loaded completely.",
        ) from exc


@router.get(
    "/flood-events/{event_id}/allocation-plans",
    response_model=list[AllocationPlanRecord],
)
async def list_allocation_plans(
    event_id: str,
    service: Annotated[AllocationPlanService, Depends(get_allocation_plan_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    skip: Annotated[int, Query(ge=0)] = 0,
) -> list[AllocationPlanRecord]:
    try:
        return await service.list_plans(event_id, limit=limit, skip=skip)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/allocation-plans/{plan_id}", response_model=AllocationPlanRecord)
async def get_allocation_plan(
    plan_id: str,
    service: Annotated[AllocationPlanService, Depends(get_allocation_plan_service)],
) -> AllocationPlanRecord:
    try:
        record = await service.get_plan(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Allocation plan not found.")
    return record


@router.post("/allocation-plans/{plan_id}/approve", response_model=AllocationPlanRecord)
async def approve_allocation_plan(
    plan_id: str,
    request: DecisionRequest,
    service: Annotated[
        AllocationApprovalService, Depends(get_allocation_approval_service)
    ],
) -> AllocationPlanRecord:
    try:
        result = await service.approve(
            plan_id, actor_id=request.actor_id, actor_type=request.actor_type,
            reason=request.reason,
        )
        return AllocationPlanRecord.model_validate(result)
    except (
        ApprovalNotFound, ApprovalConflict, ApprovalValidationError,
        ApprovalServiceUnavailable,
    ) as exc:
        _raise_approval_http_error(exc)


@router.post("/allocation-plans/{plan_id}/reject", response_model=AllocationPlanRecord)
async def reject_allocation_plan(
    plan_id: str,
    request: DecisionRequest,
    service: Annotated[
        AllocationApprovalService, Depends(get_allocation_approval_service)
    ],
) -> AllocationPlanRecord:
    try:
        result = await service.reject(
            plan_id, actor_id=request.actor_id, actor_type=request.actor_type,
            reason=request.reason,
        )
        return AllocationPlanRecord.model_validate(result)
    except (
        ApprovalNotFound, ApprovalConflict, ApprovalValidationError,
        ApprovalServiceUnavailable,
    ) as exc:
        _raise_approval_http_error(exc)
