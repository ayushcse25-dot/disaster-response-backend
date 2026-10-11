"""MongoDB repository for affected locations."""

from typing import Any
from app.exceptions import PlanningSnapshotError

from pymongo.errors import DuplicateKeyError

from app.models.affected_location import AffectedLocation, SeverityLevel


class AffectedLocationRepository:
    """Store and retrieve affected locations in MongoDB."""

    COLLECTION_NAME = "affected_locations"

    def __init__(self, database: Any) -> None:
        self.collection = database[self.COLLECTION_NAME]

    async def create(
        self,
        location: AffectedLocation,
    ) -> AffectedLocation:
        """Insert a new affected location."""

        document = location.model_dump(mode="json")
        document["_id"] = document.pop("location_id")

        try:
            await self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise ValueError(
                f"Affected location '{location.location_id}' already exists."
            ) from exc

        return location

    async def get_by_id(
        self,
        location_id: str,
    ) -> AffectedLocation | None:
        """Retrieve an affected location by its ID."""

        document = await self.collection.find_one({"_id": location_id})

        if document is None:
            return None

        document["location_id"] = document.pop("_id")

        return AffectedLocation.model_validate(document)

    async def list_for_planning(self, *, max_records: int = 5000) -> list[AffectedLocation]:
        """Load a complete bounded snapshot, failing rather than truncating."""
        if max_records < 1:
            raise ValueError("max_records must be positive.")
        docs = await self.collection.find({}).limit(max_records + 1).to_list(length=max_records + 1)
        if len(docs) > max_records:
            raise PlanningSnapshotError("Affected-location snapshot exceeds the planning limit.")
        result = []
        for doc in docs:
            doc["location_id"] = doc.pop("_id")
            result.append(AffectedLocation.model_validate(doc))
        return result

    async def list_by_event(
        self,
        event_id: str,
        *,
        limit: int = 20,
        skip: int = 0,
    ) -> list[AffectedLocation]:
        """List affected locations belonging to a flood event."""

        if not event_id or not event_id.strip():
            raise ValueError("Event ID cannot be empty.")

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")

        if skip < 0:
            raise ValueError("skip cannot be negative.")

        cursor = (
            self.collection.find({"event_id": event_id})
            .sort("last_changed_at", -1)
            .skip(skip)
            .limit(limit)
        )

        documents = await cursor.to_list(length=limit)

        locations: list[AffectedLocation] = []

        for document in documents:
            document["location_id"] = document.pop("_id")
            locations.append(AffectedLocation.model_validate(document))

        return locations

    async def severities_by_event(
        self,
        event_ids: list[str],
    ) -> dict[str, list[SeverityLevel]]:
        """Return the severity of every affected location, grouped by event ID."""

        result: dict[str, list[SeverityLevel]] = {event_id: [] for event_id in event_ids}

        if not event_ids:
            return result

        cursor = self.collection.find(
            {"event_id": {"$in": event_ids}},
            {"event_id": 1, "severity": 1},
        )

        for document in await cursor.to_list(length=None):
            result.setdefault(document["event_id"], []).append(
                SeverityLevel(document.get("severity", SeverityLevel.UNKNOWN))
            )

        return result
