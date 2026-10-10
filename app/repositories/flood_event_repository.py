from typing import Any

from pymongo.errors import DuplicateKeyError

from app.models.flood_event import FloodEvent


class FloodEventRepository:
    """Database operations for flood events."""

    COLLECTION_NAME = "flood_events"

    def __init__(self, database: Any) -> None:
        self.collection = database[self.COLLECTION_NAME]

    async def create(self, event: FloodEvent) -> FloodEvent:
        """Save a new flood event and return the validated event."""
        document = event.model_dump(mode="json")
        document["_id"] = document.pop("event_id")

        try:
            await self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise ValueError(
                f"Flood event '{event.event_id}' already exists."
            ) from exc

        return event

    async def get_by_id(self, event_id: str) -> FloodEvent | None:
        """Retrieve and validate a flood event by its ID."""
        document = await self.collection.find_one({"_id": event_id})

        if document is None:
            return None

        document["event_id"] = document.pop("_id")
        return FloodEvent.model_validate(document)

    async def list_events(
        self,
        *,
        limit: int = 20,
        skip: int = 0,
    ) -> list[FloodEvent]:
        """Return validated flood events, newest first."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")

        if skip < 0:
            raise ValueError("skip cannot be negative.")

        cursor = (
            self.collection.find({})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )

        documents = await cursor.to_list(length=limit)
        events = []

        for document in documents:
            document["event_id"] = document.pop("_id")
            events.append(FloodEvent.model_validate(document))

        return events