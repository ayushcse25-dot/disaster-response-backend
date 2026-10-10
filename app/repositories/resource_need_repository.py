"""MongoDB repository for resource needs."""

from typing import Any

from pymongo.errors import DuplicateKeyError

from app.models.resource_need import ResourceNeed


class ResourceNeedRepository:
    """Store and retrieve resource needs in MongoDB."""

    COLLECTION_NAME = "resource_needs"

    def __init__(self, database: Any) -> None:
        self.collection = database[self.COLLECTION_NAME]

    async def create(self, need: ResourceNeed) -> ResourceNeed:
        """Insert a new resource need."""

        document = need.model_dump(mode="json")
        document["_id"] = document.pop("need_id")

        try:
            await self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise ValueError(
                f"Resource need '{need.need_id}' already exists."
            ) from exc

        return need

    async def get_by_id(self, need_id: str) -> ResourceNeed | None:
        """Retrieve a resource need by its ID."""

        document = await self.collection.find_one({"_id": need_id})

        if document is None:
            return None

        document["need_id"] = document.pop("_id")

        return ResourceNeed.model_validate(document)

    async def list_by_event(
        self,
        event_id: str,
        *,
        limit: int = 20,
        skip: int = 0,
    ) -> list[ResourceNeed]:
        """List resource needs belonging to a flood event."""

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")

        if skip < 0:
            raise ValueError("skip cannot be negative.")

        cursor = (
            self.collection.find({"event_id": event_id})
            .sort("reported_at", -1)
            .skip(skip)
            .limit(limit)
        )

        documents = await cursor.to_list(length=limit)

        needs: list[ResourceNeed] = []

        for document in documents:
            document["need_id"] = document.pop("_id")
            needs.append(ResourceNeed.model_validate(document))

        return needs