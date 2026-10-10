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

    async def update_team_status(
        self,
        team_id: str,
        *,
        status,
        availability_confirmed: bool,
    ) -> ResponseTeam | None:
        """Update status and confirmation with server-generated timestamps."""

        from datetime import datetime, timezone

        from app.models.response_team import TeamStatus

        if not team_id or not team_id.strip():
            raise ValueError("Team ID cannot be empty.")

        if status in {TeamStatus.ASSIGNED, TeamStatus.DEPLOYED}:
            raise ValueError(
                "Assignment and deployment status must be managed by the "
                "assignment workflow."
            )

        if status == TeamStatus.AVAILABLE and not availability_confirmed:
            raise ValueError(
                "AVAILABLE status requires explicit availability confirmation."
            )

        if status in {
            TeamStatus.UNKNOWN,
            TeamStatus.UNAVAILABLE,
            TeamStatus.OFFLINE,
        } and availability_confirmed:
            raise ValueError(
                "This status cannot be marked as availability-confirmed."
            )

        return await self.repository.update_status(
            team_id,
            status=status,
            availability_confirmed=availability_confirmed,
            updated_at=datetime.now(timezone.utc),
        )

    async def update_team_location(
        self,
        team_id: str,
        *,
        current_location,
    ) -> ResponseTeam | None:
        """Update location without implicitly confirming availability."""

        from datetime import datetime, timezone

        if not team_id or not team_id.strip():
            raise ValueError("Team ID cannot be empty.")

        return await self.repository.update_location(
            team_id,
            current_location=current_location,
            updated_at=datetime.now(timezone.utc),
        )
