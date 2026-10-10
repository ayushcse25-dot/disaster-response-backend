"""API endpoints for resource needs."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_database
from app.models.resource_need import ResourceNeed, NeedStatus
from app.repositories.flood_event_repository import FloodEventRepository
from app.repositories.resource_need_repository import ResourceNeedRepository
from app.schemas.resource_need import ResourceNeedCreate, ResourceNeedResponse
from app.services.resource_need_service import ResourceNeedService


router = APIRouter(tags=["Resource Needs"])


def get_resource_need_service(
    database=Depends(get_database),
) -> ResourceNeedService:
    """Create the resource-need service using the application database."""

    resource_need_repository = ResourceNeedRepository(database)
    flood_event_repository = FloodEventRepository(database)

    return ResourceNeedService(
        repository=resource_need_repository,
        flood_event_repository=flood_event_repository,
    )


@router.post(
    "/api/v1/resource-needs",
    response_model=ResourceNeedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_resource_need(
    payload: ResourceNeedCreate,
    service: ResourceNeedService = Depends(get_resource_need_service),
) -> ResourceNeedResponse:
    """Report a new resource need."""

    need = ResourceNeed(
        need_id=str(uuid4()),
        event_id=payload.event_id,
        location_id=payload.location_id,
        need_type=payload.need_type,
        description=payload.description,
        urgency=payload.urgency,
        status=NeedStatus.REPORTED,
        quantity_requested=payload.quantity_requested,
        quantity_unit=payload.quantity_unit,
        supporting_observation_ids=payload.supporting_observation_ids,
    )

    try:
        created_need = await service.create_need(need)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return ResourceNeedResponse.model_validate(created_need.model_dump())


@router.get(
    "/api/v1/resource-needs/{need_id}",
    response_model=ResourceNeedResponse,
)
async def get_resource_need(
    need_id: str,
    service: ResourceNeedService = Depends(get_resource_need_service),
) -> ResourceNeedResponse:
    """Retrieve a resource need by its ID."""

    try:
        need = await service.get_need(need_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if need is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource need '{need_id}' does not exist.",
        )

    return ResourceNeedResponse.model_validate(need.model_dump())


@router.get(
    "/api/v1/flood-events/{event_id}/resource-needs",
    response_model=list[ResourceNeedResponse],
)
async def list_resource_needs(
    event_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    service: ResourceNeedService = Depends(get_resource_need_service),
) -> list[ResourceNeedResponse]:
    """List resource needs associated with a flood event."""

    try:
        needs = await service.list_needs_for_event(
            event_id,
            limit=limit,
            skip=skip,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return [
        ResourceNeedResponse.model_validate(need.model_dump())
        for need in needs
    ]
