"""Unit tests for the response-team service."""

from unittest.mock import AsyncMock

import pytest

from app.models.response_team import ResponseTeam, TeamStatus
from app.services.response_team_service import ResponseTeamService


@pytest.fixture
def sample_team() -> ResponseTeam:
    return ResponseTeam(
        team_id="team-service-001",
        organisation_id="organisation-service-001",
        team_name="Flood Rescue Team",
        personnel_count=8,
        status=TeamStatus.UNKNOWN,
        availability_confirmed=False,
    )


@pytest.fixture
def service():
    repository = AsyncMock()
    return ResponseTeamService(repository), repository


@pytest.mark.asyncio
async def test_create_team_preserves_unconfirmed_availability(
    service,
    sample_team,
):
    team_service, repository = service
    repository.create.return_value = sample_team

    result = await team_service.create_team(sample_team)

    assert result == sample_team
    assert result.status == TeamStatus.UNKNOWN
    assert result.availability_confirmed is False
    repository.create.assert_awaited_once_with(sample_team)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("team_id", "   ", "Team ID cannot be empty."),
        ("organisation_id", "   ", "Organisation ID cannot be empty."),
    ],
)
async def test_create_team_rejects_blank_identifiers(
    service,
    sample_team,
    field,
    value,
    message,
):
    team_service, repository = service
    invalid_team = sample_team.model_copy(update={field: value})

    with pytest.raises(ValueError, match=message):
        await team_service.create_team(invalid_team)

    repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_existing_team(service, sample_team):
    team_service, repository = service
    repository.get_by_id.return_value = sample_team

    result = await team_service.get_team(sample_team.team_id)

    assert result == sample_team
    repository.get_by_id.assert_awaited_once_with(sample_team.team_id)


@pytest.mark.asyncio
async def test_get_missing_team(service):
    team_service, repository = service
    repository.get_by_id.return_value = None

    result = await team_service.get_team("missing-team")

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("team_id", ["", "   "])
async def test_get_team_rejects_blank_id(service, team_id):
    team_service, repository = service

    with pytest.raises(ValueError, match="Team ID cannot be empty"):
        await team_service.get_team(team_id)

    repository.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_teams_for_organisation(service, sample_team):
    team_service, repository = service
    repository.list_by_organisation.return_value = [sample_team]

    result = await team_service.list_teams_for_organisation(
        sample_team.organisation_id,
        limit=10,
        skip=5,
    )

    assert result == [sample_team]
    repository.list_by_organisation.assert_awaited_once_with(
        sample_team.organisation_id,
        limit=10,
        skip=5, include_sample=True,
    )


@pytest.mark.asyncio
async def test_list_teams_rejects_blank_organisation(service):
    team_service, repository = service

    with pytest.raises(ValueError, match="Organisation ID cannot be empty"):
        await team_service.list_teams_for_organisation("   ")

    repository.list_by_organisation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 101])
async def test_list_teams_rejects_invalid_limit(service, limit):
    team_service, repository = service

    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        await team_service.list_teams_for_organisation(
            "organisation-service-001",
            limit=limit,
        )

    repository.list_by_organisation.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_teams_rejects_negative_skip(service):
    team_service, repository = service

    with pytest.raises(ValueError, match="skip cannot be negative"):
        await team_service.list_teams_for_organisation(
            "organisation-service-001",
            skip=-1,
        )

    repository.list_by_organisation.assert_not_awaited()
