"""Flood event API endpoints."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_database
from app.models.flood_event import FloodEvent
from app.repositories.affected_location_repository import (
    AffectedLocationRepository,
)
from app.repositories.flood_event_repository import FloodEventRepository
from app.schemas.flood_event import FloodEventCreate, FloodEventResponse
from app.services.event_severity import EventSeverity, derive_event_severity
from app.services.flood_event_service import FloodEventService


router = APIRouter(
    prefix="/api/v1/flood-events",
    tags=["flood-events"],
)


def get_flood_event_service(
    database: Annotated[AsyncDatabase, Depends(get_database)],
) -> FloodEventService:
    repository = FloodEventRepository(database)
    return FloodEventService(repository, AffectedLocationRepository(database))


def to_response(
    event: FloodEvent,
    severity: EventSeverity | None = None,
) -> FloodEventResponse:
    """Combine a stored event with its derived severity."""
    severity = severity or derive_event_severity([])
    return FloodEventResponse.model_validate(
        {**event.model_dump(), **severity.model_dump()}
    )


@router.post(
    "",
    response_model=FloodEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_flood_event(
    payload: FloodEventCreate,
    service: Annotated[
        FloodEventService,
        Depends(get_flood_event_service),
    ],
) -> FloodEventResponse:
    event = FloodEvent(
        event_id=str(uuid4()),
        **payload.model_dump(),
    )

    try:
        created_event = await service.create_event(event)
    except ValueError as exc:
        if "already exists" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A flood event with this ID already exists.",
            ) from exc
        raise

    # A new event has no affected locations yet, so its severity is UNKNOWN.
    return to_response(created_event)


@router.get("", response_model=list[FloodEventResponse])
async def list_flood_events(
    service: Annotated[
        FloodEventService,
        Depends(get_flood_event_service),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    skip: Annotated[int, Query(ge=0)] = 0,
    include_sample: Annotated[bool, Query(description="false returns only real (is_sample=false) records")] = True,
) -> list[FloodEventResponse]:
    events = await service.list_events(limit=limit, skip=skip, include_sample=include_sample)
    severities = await service.severity_for_events(
        [event.event_id for event in events]
    )

    return [to_response(event, severities.get(event.event_id)) for event in events]


@router.get("/{event_id}", response_model=FloodEventResponse)
async def get_flood_event(
    event_id: str,
    service: Annotated[
        FloodEventService,
        Depends(get_flood_event_service),
    ],
) -> FloodEventResponse:
    event = await service.get_event(event_id)

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flood event not found.",
        )

    severities = await service.severity_for_events([event.event_id])

    return to_response(event, severities.get(event.event_id))