from app.models.flood_event import FloodEvent
from app.repositories.flood_event_repository import FloodEventRepository


class FloodEventService:
    """Application-level operations for flood events."""

    def __init__(self, repository: FloodEventRepository) -> None:
        self.repository = repository

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
    