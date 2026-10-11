"""Read observations for a flood event, joined with the source registry."""

from datetime import datetime, timedelta, timezone

from app.models.flood_observation import FloodObservation
from app.models.source import SourceRegistryEntry
from app.repositories.flood_event_repository import FloodEventRepository
from app.repositories.flood_observation_repository import (
    FloodObservationRepository,
)
from app.repositories.source_repository import SourceRepository
from app.schemas.flood_observation import (
    FRESHNESS_RULE,
    FloodObservationResponse,
    Freshness,
)


def classify_freshness(observed_at: datetime, now: datetime) -> Freshness:
    """Apply FRESHNESS_RULE."""
    age = now - observed_at

    if age < timedelta(hours=1):
        return Freshness.FRESH

    if age < timedelta(hours=24):
        return Freshness.RECENT

    return Freshness.STALE


def to_response(
    observation: FloodObservation,
    source: SourceRegistryEntry | None,
    now: datetime,
) -> FloodObservationResponse:
    data = observation.model_dump(exclude={"evidence_reference"})

    return FloodObservationResponse.model_validate(
        {
            **data,
            "source_name": source.name if source else None,
            "source_category": source.category if source else None,
            "source_approval_status": source.approval_status if source else None,
            "freshness": classify_freshness(observation.observed_at, now),
            "freshness_rule": FRESHNESS_RULE,
        }
    )


class FloodObservationService:
    def __init__(
        self,
        event_repository: FloodEventRepository,
        observation_repository: FloodObservationRepository,
        source_repository: SourceRepository,
    ) -> None:
        self.event_repository = event_repository
        self.observation_repository = observation_repository
        self.source_repository = source_repository

    async def list_for_event(
        self,
        event_id: str,
        *,
        limit: int = 50,
        skip: int = 0,
        now: datetime | None = None,
        include_sample: bool = True,
    ) -> list[FloodObservationResponse] | None:
        """Return the event's observations, or None if the event does not exist."""

        if await self.event_repository.get_by_id(event_id) is None:
            return None

        observations = await self.observation_repository.list_by_event(
            event_id, limit=limit, skip=skip, include_sample=include_sample
        )
        sources = await self.source_repository.get_many(
            [observation.source_id for observation in observations]
        )
        now = now or datetime.now(timezone.utc)

        return [
            to_response(observation, sources.get(observation.source_id), now)
            for observation in observations
        ]
