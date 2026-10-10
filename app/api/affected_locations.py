"""API endpoints for affected locations."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_database
from app.models.affected_location import AffectedLocation
from app.repositories.affected_location_repository import (
    AffectedLocationRepository,
)
from app.repositories.flood_event_repository import FloodEventRepository
from app.schemas.affected_location import (
    AffectedLocationCreate,
    AffectedLocationResponse,
)
from app.services.affected_location_service import AffectedLocationService


router = APIRouter(tags=["Affected Locations"])


def get_affected_location_service(
    database=Depends(get_database),
) -> AffectedLocationService:
    """Build the affected-location service using the application database."""

    repository = AffectedLocationRepository(database)
    flood_event_repository = FloodEventRepository(database)

    return AffectedLocationService(
        repository=repository,
        flood_event_repository=flood_event_repository,
    )


@router.post(
    "/api/v1/affected-locations",
    response_model=AffectedLocationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_affected_location(
    payload: AffectedLocationCreate,
    service: AffectedLocationService = Depends(
        get_affected_location_service
    ),
) -> AffectedLocationResponse:
    """Register a location affected by a flood."""

    location = AffectedLocation(
        location_id=str(uuid4()),
        event_id=payload.event_id,
        location_name=payload.location_name,
        state=payload.state,
        district=payload.district,
        coordinates=payload.coordinates,
        severity=payload.severity,
        supporting_observation_ids=payload.supporting_observation_ids,
    )

    try:
        created_location = await service.create_location(location)
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

    return AffectedLocationResponse.model_validate(
        created_location.model_dump()
    )


@router.get(
    "/api/v1/affected-locations/{location_id}",
    response_model=AffectedLocationResponse,
)
async def get_affected_location(
    location_id: str,
    service: AffectedLocationService = Depends(
        get_affected_location_service
    ),
) -> AffectedLocationResponse:
    """Retrieve an affected location by ID."""

    try:
        location = await service.get_location(location_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Affected location '{location_id}' does not exist.",
        )

    return AffectedLocationResponse.model_validate(location.model_dump())


@router.get(
    "/api/v1/flood-events/{event_id}/affected-locations",
    response_model=list[AffectedLocationResponse],
)
async def list_affected_locations(
    event_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    service: AffectedLocationService = Depends(
        get_affected_location_service
    ),
) -> list[AffectedLocationResponse]:
    """List affected locations associated with a flood event."""

    try:
        locations = await service.list_locations_for_event(
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
        AffectedLocationResponse.model_validate(location.model_dump())
        for location in locations
    ]
