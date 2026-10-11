"""Business logic for resource inventory."""

from app.models.resource_inventory import (
    InventoryStatus,
    ResourceInventory,
)
from app.repositories.resource_inventory_repository import (
    ResourceInventoryRepository,
)


class ResourceInventoryService:
    """Manage resource inventory records."""

    def __init__(self, repository: ResourceInventoryRepository) -> None:
        self.repository = repository

    async def create_inventory(
        self,
        inventory: ResourceInventory,
    ) -> ResourceInventory:
        """Register inventory without assuming availability is verified."""

        if not inventory.organisation_id.strip():
            raise ValueError("Organisation ID cannot be empty.")

        if inventory.quantity_reserved != 0 or inventory.quantity_deployed != 0:
            raise ValueError(
                "New inventory cannot start with reserved or deployed stock."
            )

        if inventory.availability_confirmed:
            raise ValueError(
                "New inventory must be verified through a separate process."
            )

        if inventory.status != InventoryStatus.UNKNOWN:
            raise ValueError(
                "New inventory must start with UNKNOWN status."
            )

        return await self.repository.create(inventory)

    async def get_inventory(
        self,
        inventory_id: str,
    ) -> ResourceInventory | None:
        """Retrieve inventory by ID."""

        if not inventory_id or not inventory_id.strip():
            raise ValueError("Inventory ID cannot be empty.")

        return await self.repository.get_by_id(inventory_id)

    async def list_inventory(
        self,
        organisation_id: str,
        *,
        limit: int = 20,
        skip: int = 0,
        include_sample: bool = True,
    ) -> list[ResourceInventory]:
        """List inventory belonging to an organisation."""

        if not organisation_id or not organisation_id.strip():
            raise ValueError("Organisation ID cannot be empty.")

        return await self.repository.list_by_organisation(
            organisation_id,
            limit=limit,
            skip=skip,
            include_sample=include_sample,
        )
