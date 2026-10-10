"""Business logic for affected locations."""

from app.models.affected_location import AffectedLocation
from app.repositories.affected_location_repository import (
    AffectedLocationRepository,
)
from app.repositories.flood_event_repository import FloodEventRepository


class AffectedLocationService:
    """Manage affected locations associated with flood events."""

    def __init__(
        self,
        repository: AffectedLocationRepository,
        flood_event_repository: FloodEventRepository,
    ) -> None:
        self.repository = repository
        self.flood_event_repository = flood_event_repository

    async def create_location(
        self,
        location: AffectedLocation,
    ) -> AffectedLocation:
        """Create a location only when its flood event exists."""

        event_id = location.event_id

        if not event_id or not event_id.strip():
            raise ValueError("Event ID cannot be empty.")

        event = await self.flood_event_repository.get_by_id(event_id)

        if event is None:
            raise LookupError(
                f"Flood event '{event_id}' does not exist."
            )

        return await self.repository.create(location)

    async def get_location(
        self,
        location_id: str,
    ) -> AffectedLocation | None:
        """Retrieve an affected location by ID."""

        if not location_id or not location_id.strip():
            raise ValueError("Location ID cannot be empty.")

        return await self.repository.get_by_id(location_id)

    async def list_locations_for_event(
        self,
        event_id: str,
        *,
        limit: int = 20,
        skip: int = 0,
    ) -> list[AffectedLocation]:
        """List affected locations associated with an existing event."""

        if not event_id or not event_id.strip():
            raise ValueError("Event ID cannot be empty.")

        event = await self.flood_event_repository.get_by_id(event_id)

        if event is None:
            raise LookupError(
                f"Flood event '{event_id}' does not exist."
            )

        return await self.repository.list_by_event(
            event_id,
            limit=limit,
            skip=skip,
        )
