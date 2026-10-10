"""MongoDB repository for response teams."""

from typing import Any

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
