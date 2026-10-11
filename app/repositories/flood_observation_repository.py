"""MongoDB repository for flood observations."""

from typing import Any

from app.models.flood_observation import FloodObservation


class FloodObservationRepository:
    """Read flood observations from MongoDB."""

    COLLECTION_NAME = "flood_observations"

    def __init__(self, database: Any) -> None:
        self.collection = database[self.COLLECTION_NAME]

    async def list_by_event(
        self,
        event_id: str,
        *,
        limit: int = 50,
        skip: int = 0,
    ) -> list[FloodObservation]:
        """List observations linked to a flood event, newest observed first."""

        if not event_id or not event_id.strip():
            raise ValueError("Event ID cannot be empty.")

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")

        if skip < 0:
            raise ValueError("skip cannot be negative.")

        cursor = (
            self.collection.find({"event_id": event_id})
            .sort("observed_at", -1)
            .skip(skip)
            .limit(limit)
        )

        observations: list[FloodObservation] = []

        for document in await cursor.to_list(length=limit):
            document["observation_id"] = document.pop("_id")
            observations.append(FloodObservation.model_validate(document))

        return observations
