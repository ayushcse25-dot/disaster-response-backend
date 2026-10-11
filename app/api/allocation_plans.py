"""Endpoints for allocation proposals and human approval decisions."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_database
from app.exceptions import PlanningSnapshotError
from app.api.auth_deps import CurrentUser, ensure_ngo_scope, require_roles
from app.core.errors import ApiError
from app.models.user import Role
from app.models.allocation_plan import AllocationPlanRecord, AllocationPlanView
from app.repositories.affected_location_repository import AffectedLocationRepository
from app.repositories.allocation_plan_repository import AllocationPlanRepository
from app.repositories.flood_event_repository import FloodEventRepository
from app.repositories.resource_inventory_repository import ResourceInventoryRepository
from app.repositories.resource_need_repository import ResourceNeedRepository
from app.repositories.response_team_repository import ResponseTeamRepository
from app.services.allocation_plan_service import AllocationPlanService
from app.services.plan_lifecycle_service import (
    ManualAllocationItem,
    PlanLifecycleError,
    PlanLifecycleService,
    PlanNotFound,
    PlanVersionConflict,
)
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


def get_plan_lifecycle_service(
    database: Annotated[AsyncDatabase, Depends(get_database)],
    plan_service: Annotated[AllocationPlanService, Depends(get_allocation_plan_service)],
) -> PlanLifecycleService:
    return PlanLifecycleService(database, plan_service)


class ReplanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    actor_id: str = Field(min_length=1, max_length=100)


class ManualAllocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    actor_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=3000)
    items: list[ManualAllocationItem] = Field(min_length=1, max_length=100)


def _raise_lifecycle_error(exc: PlanLifecycleError) -> None:
    if isinstance(exc, PlanNotFound):
        raise ApiError(404, exc.code, exc.detail) from exc
    if isinstance(exc, PlanVersionConflict):
        raise ApiError(409, exc.code, exc.detail) from exc
    raise ApiError(422, exc.code, exc.detail) from exc


async def _check_plan_scope(database: AsyncDatabase, user, plan_id: str) -> None:
    if user.role == Role.AUTHORITY:
        return
    document = await database["allocation_plans"].find_one({"_id": plan_id}, {"ngo_id": 1})
    if document is None:
        raise ApiError(404, "PLAN_NOT_FOUND", "Allocation plan not found.")
    ensure_ngo_scope(user, document.get("ngo_id"))


async def plan_scope(plan_id: str, user: CurrentUser, request: Request) -> None:
    """NGO staff may act only on plans that use their organisation's resources."""
    if user.role != Role.AUTHORITY:
        await _check_plan_scope(get_database(request), user, plan_id)


PlanScope = Depends(plan_scope)


def get_allocation_approval_service(
    database: Annotated[AsyncDatabase, Depends(get_database)],
) -> AllocationApprovalService:
    return AllocationApprovalService(database)


def _raise_approval_http_error(exc: Exception) -> None:
    if isinstance(exc, ApprovalNotFound):
        raise ApiError(404, "PLAN_NOT_FOUND", str(exc)) from exc
    if isinstance(exc, ApprovalConflict):
        raise ApiError(409, "APPROVAL_CONFLICT", str(exc)) from exc
    if isinstance(exc, ApprovalValidationError):
        raise ApiError(422, "APPROVAL_INVALID", str(exc)) from exc
    if isinstance(exc, ApprovalServiceUnavailable):
        raise ApiError(
            503,
            "TRANSACTION_UNAVAILABLE",
            detail="The decision could not be persisted; do not treat it as committed.",
        ) from exc
    raise exc


@router.post(
    "/flood-events/{event_id}/allocation-plans",
    response_model=AllocationPlanRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(Role.AUTHORITY))],
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
    response_model=list[AllocationPlanView],
)
async def list_allocation_plans(
    event_id: str,
    service: Annotated[AllocationPlanService, Depends(get_allocation_plan_service)],
    lifecycle: Annotated[PlanLifecycleService, Depends(get_plan_lifecycle_service)],
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    skip: Annotated[int, Query(ge=0)] = 0,
) -> list[AllocationPlanView]:
    try:
        records = await service.list_plans(event_id, limit=limit, skip=skip)
        if user.role != Role.AUTHORITY:
            records = [r for r in records if r.ngo_id and r.ngo_id == user.ngo_id]
        return [await lifecycle.view(record) for record in records]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/allocation-plans/{plan_id}", response_model=AllocationPlanView)
async def get_allocation_plan(
    plan_id: str,
    service: Annotated[AllocationPlanService, Depends(get_allocation_plan_service)],
    lifecycle: Annotated[PlanLifecycleService, Depends(get_plan_lifecycle_service)],
    user: CurrentUser,
) -> AllocationPlanView:
    try:
        record = await service.get_plan(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise ApiError(404, "PLAN_NOT_FOUND", "Allocation plan not found.")
    ensure_ngo_scope(user, record.ngo_id)
    return await lifecycle.view(record)


@router.post(
    "/allocation-plans/{plan_id}/replan",
    response_model=AllocationPlanRecord,
    dependencies=[PlanScope],
    status_code=status.HTTP_201_CREATED,
)
async def replan_allocation_plan(
    plan_id: str,
    request: ReplanRequest,
    lifecycle: Annotated[PlanLifecycleService, Depends(get_plan_lifecycle_service)],
) -> AllocationPlanRecord:
    """Re-run the engine and store the result as the next plan version."""
    try:
        return await lifecycle.replan(
            plan_id, expected_version=request.expected_version, actor_id=request.actor_id
        )
    except PlanLifecycleError as exc:
        _raise_lifecycle_error(exc)
    except PlanningSnapshotError as exc:
        raise ApiError(503, "SNAPSHOT_UNAVAILABLE", "The planning snapshot could not be loaded completely.") from exc


@router.post(
    "/allocation-plans/{plan_id}/manual-allocation",
    response_model=AllocationPlanRecord,
    dependencies=[PlanScope],
    status_code=status.HTTP_201_CREATED,
)
async def manual_allocation(
    plan_id: str,
    request: ManualAllocationRequest,
    lifecycle: Annotated[PlanLifecycleService, Depends(get_plan_lifecycle_service)],
) -> AllocationPlanRecord:
    """Store a human-chosen allocation as the next plan version (source=MANUAL)."""
    try:
        return await lifecycle.manual_allocation(
            plan_id,
            expected_version=request.expected_version,
            actor_id=request.actor_id,
            reason=request.reason,
            items=request.items,
        )
    except PlanLifecycleError as exc:
        _raise_lifecycle_error(exc)


@router.post("/allocation-plans/{plan_id}/approve", response_model=AllocationPlanRecord, dependencies=[PlanScope])
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


@router.post("/allocation-plans/{plan_id}/reject", response_model=AllocationPlanRecord, dependencies=[PlanScope])
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
