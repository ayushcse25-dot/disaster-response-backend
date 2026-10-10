"""MongoDB repository for response teams."""

from typing import Any
from app.exceptions import PlanningSnapshotError

from pymongo.errors import DuplicateKeyError

from app.models.response_team import ResponseTeam


class ResponseTeamRepository:
    """Store and retrieve registered response teams in MongoDB."""

    COLLECTION_NAME = "response_teams"

    def __init__(self, database: Any) -> None:
        self.collection = database[self.COLLECTION_NAME]

    async def create(self, team: ResponseTeam) -> ResponseTeam:
        """Register a response team without changing its availability."""

        document = team.model_dump(mode="json")
        document["_id"] = document.pop("team_id")

        try:
            await self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise ValueError(
                f"Response team '{team.team_id}' already exists."
            ) from exc

        return team

    async def get_by_id(self, team_id: str) -> ResponseTeam | None:
        """Retrieve a response team by its ID."""

        document = await self.collection.find_one({"_id": team_id})

        if document is None:
            return None

        document["team_id"] = document.pop("_id")

        return ResponseTeam.model_validate(document)

    async def list_for_planning(self, *, max_records: int = 5000) -> list[ResponseTeam]:
        """Load a complete bounded snapshot, failing rather than truncating."""
        if max_records < 1:
            raise ValueError("max_records must be positive.")
        docs = await self.collection.find({}).limit(max_records + 1).to_list(length=max_records + 1)
        if len(docs) > max_records:
            raise PlanningSnapshotError("Response-team snapshot exceeds the planning limit.")
        result = []
        for doc in docs:
            doc["team_id"] = doc.pop("_id")
            result.append(ResponseTeam.model_validate(doc))
        return result

    async def list_by_organisation(
        self,
        organisation_id: str,
        *,
        limit: int = 20,
        skip: int = 0,
    ) -> list[ResponseTeam]:
        """List response teams registered by an organisation."""

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

        teams: list[ResponseTeam] = []

        for document in documents:
            document["team_id"] = document.pop("_id")
            teams.append(ResponseTeam.model_validate(document))

        return teams

    async def update_status(
        self,
        team_id: str,
        *,
        status,
        availability_confirmed: bool,
        updated_at,
    ) -> ResponseTeam | None:
        """Update operational status without changing assignment state."""

        from pymongo import ReturnDocument

        query = {"_id": team_id}

        # The assignment condition is checked atomically with the update.
        # This prevents a currently assigned team from being marked AVAILABLE.
        if status.value == "AVAILABLE":
            query["current_assignment_id"] = None

        document = await self.collection.find_one_and_update(
            query,
            {
                "$set": {
                    "status": status.value,
                    "availability_confirmed": availability_confirmed,
                    "last_status_update": updated_at.isoformat(),
                    "updated_at": updated_at.isoformat(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )

        if document is None:
            existing = await self.collection.find_one({"_id": team_id})

            if existing is None:
                return None

            if (
                status.value == "AVAILABLE"
                and existing.get("current_assignment_id") is not None
            ):
                raise ValueError(
                    "A team with a current assignment cannot be marked AVAILABLE."
                )

            return None

        document["team_id"] = document.pop("_id")
        return ResponseTeam.model_validate(document)

    async def update_location(
        self,
        team_id: str,
        *,
        current_location,
        updated_at,
    ) -> ResponseTeam | None:
        """Update location without changing status or availability."""

        from pymongo import ReturnDocument

        document = await self.collection.find_one_and_update(
            {"_id": team_id},
            {
                "$set": {
                    "current_location": current_location.model_dump(mode="json"),
                    "last_location_update": updated_at.isoformat(),
                    "updated_at": updated_at.isoformat(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )

        if document is None:
            return None

        document["team_id"] = document.pop("_id")
        return ResponseTeam.model_validate(document)
