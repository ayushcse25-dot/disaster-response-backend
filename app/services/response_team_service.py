"""Business logic for response-team registration and retrieval."""

from app.models.response_team import ResponseTeam
from app.repositories.response_team_repository import ResponseTeamRepository


class ResponseTeamService:
    """Validate response-team operations before repository access."""

    def __init__(self, repository: ResponseTeamRepository) -> None:
        self.repository = repository

    async def create_team(self, team: ResponseTeam) -> ResponseTeam:
        """Register a response team without asserting its availability."""

        if not team.team_id.strip():
            raise ValueError("Team ID cannot be empty.")

        if not team.organisation_id.strip():
            raise ValueError("Organisation ID cannot be empty.")

        return await self.repository.create(team)

    async def get_team(self, team_id: str) -> ResponseTeam | None:
        """Retrieve a response team by its ID."""

        if not team_id or not team_id.strip():
            raise ValueError("Team ID cannot be empty.")

        return await self.repository.get_by_id(team_id)

    async def list_teams_for_organisation(
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

        return await self.repository.list_by_organisation(
            organisation_id,
            limit=limit,
            skip=skip,
        )
