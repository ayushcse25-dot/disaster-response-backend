"""MongoDB repository for resource inventory."""

from typing import Any

from pymongo.errors import DuplicateKeyError

from app.models.resource_inventory import ResourceInventory


class ResourceInventoryRepository:
    """Store and retrieve resource inventory in MongoDB."""

    COLLECTION_NAME = "resource_inventory"

    def __init__(self, database: Any) -> None:
        self.collection = database[self.COLLECTION_NAME]

    async def create(
        self,
        inventory: ResourceInventory,
    ) -> ResourceInventory:
        """Insert a new inventory record."""

        document = inventory.model_dump(mode="json")
        document["_id"] = document.pop("inventory_id")

        try:
            await self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise ValueError(
                f"Inventory record '{inventory.inventory_id}' already exists."
            ) from exc

        return inventory

    async def get_by_id(
        self,
        inventory_id: str,
    ) -> ResourceInventory | None:
        """Retrieve an inventory record by its ID."""

        document = await self.collection.find_one({"_id": inventory_id})

        if document is None:
            return None

        document["inventory_id"] = document.pop("_id")

        return ResourceInventory.model_validate(document)

    async def list_by_organisation(
        self,
        organisation_id: str,
        *,
        limit: int = 20,
        skip: int = 0,
    ) -> list[ResourceInventory]:
        """List inventory records belonging to an organisation."""

        if not organisation_id or not organisation_id.strip():
            raise ValueError("Organisation ID cannot be empty.")

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")

        if skip < 0:
            raise ValueError("skip cannot be negative.")

        cursor = (
            self.collection.find({"organisation_id": organisation_id})
            .sort("updated_at", -1)
            .skip(skip)
            .limit(limit)
        )

        documents = await cursor.to_list(length=limit)

        inventory_records: list[ResourceInventory] = []

        for document in documents:
            document["inventory_id"] = document.pop("_id")
            inventory_records.append(
                ResourceInventory.model_validate(document)
            )

        return inventory_records
