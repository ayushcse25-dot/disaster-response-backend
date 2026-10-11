from app.models.flood_event import FloodEvent
from app.repositories.affected_location_repository import (
    AffectedLocationRepository,
)
from app.repositories.flood_event_repository import FloodEventRepository
from app.services.event_severity import EventSeverity, derive_event_severity


class FloodEventService:
    """Application-level operations for flood events."""

    def __init__(
        self,
        repository: FloodEventRepository,
        location_repository: AffectedLocationRepository | None = None,
    ) -> None:
        self.repository = repository
        self.location_repository = location_repository

    async def create_event(self, event: FloodEvent) -> FloodEvent:
        """Create a flood event through the repository."""
        return await self.repository.create(event)

    async def get_event(self, event_id: str) -> FloodEvent | None:
        """Retrieve a flood event by its ID."""
        if not event_id or not event_id.strip():
            raise ValueError("Event ID cannot be empty.")

        return await self.repository.get_by_id(event_id)

    async def list_events(
        self,
        *,
        limit: int = 20,
        skip: int = 0,
    ) -> list[FloodEvent]:
        """List flood events with pagination."""
        return await self.repository.list_events(
            limit=limit,
            skip=skip,
        )

    async def severity_for_events(
        self,
        event_ids: list[str],
    ) -> dict[str, EventSeverity]:
        """Derive each event's severity from its affected locations."""
        if self.location_repository is None:
            levels_by_event = {event_id: [] for event_id in event_ids}
        else:
            levels_by_event = await self.location_repository.severities_by_event(
                event_ids
            )

        return {
            event_id: derive_event_severity(levels_by_event.get(event_id, []))
            for event_id in event_ids
        }
