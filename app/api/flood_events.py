"""Flood event API endpoints."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_database
from app.models.flood_event import FloodEvent
from app.repositories.flood_event_repository import FloodEventRepository
from app.schemas.flood_event import FloodEventCreate, FloodEventResponse
from app.services.flood_event_service import FloodEventService


router = APIRouter(
    prefix="/api/v1/flood-events",
    tags=["flood-events"],
)


def get_flood_event_service(
    database: Annotated[AsyncDatabase, Depends(get_database)],
) -> FloodEventService:
    repository = FloodEventRepository(database)
    return FloodEventService(repository)


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

    return FloodEventResponse.model_validate(
        created_event.model_dump()
    )


@router.get("", response_model=list[FloodEventResponse])
async def list_flood_events(
    service: Annotated[
        FloodEventService,
        Depends(get_flood_event_service),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    skip: Annotated[int, Query(ge=0)] = 0,
) -> list[FloodEventResponse]:
    events = await service.list_events(limit=limit, skip=skip)

    return [
        FloodEventResponse.model_validate(event.model_dump())
        for event in events
    ]


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

    return FloodEventResponse.model_validate(event.model_dump())