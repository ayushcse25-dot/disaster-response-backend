"""Read-only flood observation endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_database
from app.repositories.flood_event_repository import FloodEventRepository
from app.repositories.flood_observation_repository import (
    FloodObservationRepository,
)
from app.repositories.source_repository import SourceRepository
from app.schemas.flood_observation import FloodObservationResponse
from app.services.flood_observation_service import FloodObservationService

router = APIRouter(prefix="/api/v1", tags=["flood-events"])


def get_flood_observation_service(
    database: Annotated[AsyncDatabase, Depends(get_database)],
) -> FloodObservationService:
    return FloodObservationService(
        FloodEventRepository(database),
        FloodObservationRepository(database),
        SourceRepository(database),
    )


@router.get(
    "/flood-events/{event_id}/observations",
    response_model=list[FloodObservationResponse],
)
async def list_flood_event_observations(
    event_id: str,
    service: Annotated[
        FloodObservationService,
        Depends(get_flood_observation_service),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    skip: Annotated[int, Query(ge=0)] = 0,
) -> list[FloodObservationResponse]:
    observations = await service.list_for_event(event_id, limit=limit, skip=skip)

    if observations is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flood event not found.",
        )

    return observations
