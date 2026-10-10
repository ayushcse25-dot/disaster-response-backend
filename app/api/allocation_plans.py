"""Endpoints for persisted allocation proposals."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.asynchronous.database import AsyncDatabase

from app.exceptions import PlanningSnapshotError
from app.api.deps import get_database
from app.models.allocation_plan import AllocationPlanRecord
from app.repositories.affected_location_repository import AffectedLocationRepository
from app.repositories.allocation_plan_repository import AllocationPlanRepository
from app.repositories.flood_event_repository import FloodEventRepository
from app.repositories.resource_inventory_repository import ResourceInventoryRepository
from app.repositories.resource_need_repository import ResourceNeedRepository
from app.repositories.response_team_repository import ResponseTeamRepository
from app.services.allocation_plan_service import AllocationPlanService

router = APIRouter(prefix="/api/v1", tags=["Allocation Plans"])


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
