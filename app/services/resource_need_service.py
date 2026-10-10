"""Business logic for resource needs."""

from app.models.resource_need import ResourceNeed
from app.repositories.flood_event_repository import FloodEventRepository
from app.repositories.resource_need_repository import ResourceNeedRepository


class ResourceNeedService:
    """Manage resource needs associated with flood events."""

    def __init__(
        self,
        repository: ResourceNeedRepository,
        flood_event_repository: FloodEventRepository,
    ) -> None:
        self.repository = repository
        self.flood_event_repository = flood_event_repository

    async def create_need(self, need: ResourceNeed) -> ResourceNeed:
        """Create a resource need only for an existing flood event."""

        event = await self.flood_event_repository.get_by_id(need.event_id)

        if event is None:
            raise LookupError(
                f"Flood event '{need.event_id}' does not exist."
            )

        return await self.repository.create(need)

    async def get_need(self, need_id: str) -> ResourceNeed | None:
        """Retrieve a resource need by ID."""

        if not need_id or not need_id.strip():
            raise ValueError("Need ID cannot be empty.")

        return await self.repository.get_by_id(need_id)

    async def list_needs_for_event(
        self,
        event_id: str,
        *,
        limit: int = 20,
        skip: int = 0,
    ) -> list[ResourceNeed]:
        """List resource needs associated with a flood event."""

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