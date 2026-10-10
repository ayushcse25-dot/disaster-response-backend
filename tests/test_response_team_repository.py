"""Unit tests for the response-team repository."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from app.models.flood_event import GeoLocation
from app.models.response_team import (
    ResponseTeam,
    TeamCapability,
    TeamStatus,
)
from app.repositories.response_team_repository import ResponseTeamRepository


@pytest.fixture
def sample_team() -> ResponseTeam:
    now = datetime.now(timezone.utc)

    return ResponseTeam(
        team_id="team-test-001",
        organisation_id="organisation-test-001",
        team_name="Flood Rescue Team",
        capabilities=[TeamCapability.WATER_RESCUE, TeamCapability.EVACUATION],
        equipment=["Rescue boat", "Life jackets"],
        personnel_count=8,
        status=TeamStatus.UNKNOWN,
        availability_confirmed=False,
        last_status_update=now,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def repository():
    database = MagicMock()
    collection = MagicMock()
    collection.insert_one = AsyncMock()
    collection.find_one = AsyncMock()
    database.__getitem__.return_value = collection

    return ResponseTeamRepository(database), collection


@pytest.mark.asyncio
async def test_create_response_team(repository, sample_team):
    repo, collection = repository

    result = await repo.create(sample_team)

    assert result == sample_team
    collection.insert_one.assert_awaited_once()

    document = collection.insert_one.await_args.args[0]
    assert document["_id"] == sample_team.team_id
    assert "team_id" not in document
    assert document["organisation_id"] == sample_team.organisation_id
    assert document["availability_confirmed"] is False
    assert document["status"] == TeamStatus.UNKNOWN.value


@pytest.mark.asyncio
async def test_create_duplicate_team(repository, sample_team):
    repo, collection = repository
    collection.insert_one.side_effect = DuplicateKeyError("duplicate key")

    with pytest.raises(ValueError, match="already exists"):
        await repo.create(sample_team)


@pytest.mark.asyncio
async def test_get_existing_team(repository, sample_team):
    repo, collection = repository
    document = sample_team.model_dump(mode="json")
    document["_id"] = document.pop("team_id")
    collection.find_one.return_value = document

    result = await repo.get_by_id(sample_team.team_id)

    collection.find_one.assert_awaited_once_with(
        {"_id": sample_team.team_id}
    )
    assert result is not None
    assert result.team_id == sample_team.team_id
    assert result.organisation_id == sample_team.organisation_id
    assert TeamCapability.WATER_RESCUE in result.capabilities


@pytest.mark.asyncio
async def test_get_missing_team(repository):
    repo, collection = repository
    collection.find_one.return_value = None

    result = await repo.get_by_id("missing-team")

    assert result is None


@pytest.mark.asyncio
async def test_list_teams_by_organisation(repository, sample_team):
    repo, collection = repository
    document = sample_team.model_dump(mode="json")
    document["_id"] = document.pop("team_id")

    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[document])
    collection.find.return_value = cursor

    result = await repo.list_by_organisation(
        sample_team.organisation_id,
        limit=10,
        skip=5,
    )

    collection.find.assert_called_once_with(
        {"organisation_id": sample_team.organisation_id}
    )
    cursor.sort.assert_called_once_with("updated_at", -1)
    cursor.skip.assert_called_once_with(5)
    cursor.limit.assert_called_once_with(10)
    cursor.to_list.assert_awaited_once_with(length=10)

    assert len(result) == 1
    assert result[0].team_id == sample_team.team_id


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 101])
async def test_list_teams_rejects_invalid_limit(repository, limit):
    repo, _ = repository

    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        await repo.list_by_organisation(
            "organisation-test-001",
            limit=limit,
        )


@pytest.mark.asyncio
async def test_list_teams_rejects_negative_skip(repository):
    repo, _ = repository

    with pytest.raises(ValueError, match="skip cannot be negative"):
        await repo.list_by_organisation(
            "organisation-test-001",
            skip=-1,
        )


@pytest.mark.asyncio
async def test_list_teams_rejects_empty_organisation(repository):
    repo, _ = repository

    with pytest.raises(ValueError, match="Organisation ID cannot be empty"):
        await repo.list_by_organisation("   ")

def make_mongo_document(team: ResponseTeam, **overrides) -> dict:
    """Create an independent MongoDB-shaped document for repository tests."""

    document = team.model_dump(mode="json")
    document["_id"] = document.pop("team_id")
    document.update(overrides)
    return document


@pytest.mark.asyncio
async def test_update_status_saves_confirmation_and_timestamps(
    repository,
    sample_team,
):
    from pymongo import ReturnDocument

    repo, collection = repository
    now = datetime.now(timezone.utc)
    document = make_mongo_document(
        sample_team,
        status=TeamStatus.AVAILABLE.value,
        availability_confirmed=True,
        last_status_update=now.isoformat(),
        updated_at=now.isoformat(),
    )
    collection.find_one_and_update = AsyncMock(return_value=document)

    result = await repo.update_status(
        sample_team.team_id,
        status=TeamStatus.AVAILABLE,
        availability_confirmed=True,
        updated_at=now,
    )

    collection.find_one_and_update.assert_awaited_once_with(
        {
            "_id": sample_team.team_id,
            "current_assignment_id": None,
        },
        {
            "$set": {
                "status": "AVAILABLE",
                "availability_confirmed": True,
                "last_status_update": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    assert result is not None
    assert result.team_id == sample_team.team_id
    assert result.status == TeamStatus.AVAILABLE
    assert result.availability_confirmed is True
    assert result.last_status_update == now


@pytest.mark.asyncio
async def test_update_status_does_not_add_assignment_filter_for_unavailable_team(
    repository,
    sample_team,
):
    from pymongo import ReturnDocument

    repo, collection = repository
    now = datetime.now(timezone.utc)
    document = make_mongo_document(
        sample_team,
        status=TeamStatus.UNAVAILABLE.value,
        availability_confirmed=False,
        last_status_update=now.isoformat(),
        updated_at=now.isoformat(),
    )
    collection.find_one_and_update = AsyncMock(return_value=document)

    result = await repo.update_status(
        sample_team.team_id,
        status=TeamStatus.UNAVAILABLE,
        availability_confirmed=False,
        updated_at=now,
    )

    query = collection.find_one_and_update.await_args.args[0]
    assert query == {"_id": sample_team.team_id}
    assert collection.find_one_and_update.await_args.kwargs[
        "return_document"
    ] == ReturnDocument.AFTER
    assert result is not None
    assert result.status == TeamStatus.UNAVAILABLE
    assert result.availability_confirmed is False


@pytest.mark.asyncio
async def test_update_status_returns_none_for_missing_team(
    repository,
):
    repo, collection = repository
    collection.find_one_and_update = AsyncMock(return_value=None)
    collection.find_one.return_value = None

    result = await repo.update_status(
        "missing-team",
        status=TeamStatus.UNAVAILABLE,
        availability_confirmed=False,
        updated_at=datetime.now(timezone.utc),
    )

    assert result is None
    collection.find_one.assert_awaited_once_with({"_id": "missing-team"})


@pytest.mark.asyncio
async def test_update_status_rejects_available_for_assigned_team(
    repository,
    sample_team,
):
    repo, collection = repository
    collection.find_one_and_update = AsyncMock(return_value=None)
    collection.find_one.return_value = {
        "_id": sample_team.team_id,
        "current_assignment_id": "assignment-001",
    }

    with pytest.raises(
        ValueError,
        match="current assignment cannot be marked AVAILABLE",
    ):
        await repo.update_status(
            sample_team.team_id,
            status=TeamStatus.AVAILABLE,
            availability_confirmed=True,
            updated_at=datetime.now(timezone.utc),
        )

    query = collection.find_one_and_update.await_args.args[0]
    assert query == {
        "_id": sample_team.team_id,
        "current_assignment_id": None,
    }
    collection.find_one.assert_awaited_once_with(
        {"_id": sample_team.team_id}
    )


@pytest.mark.asyncio
async def test_update_location_changes_coordinates_without_changing_status(
    repository,
    sample_team,
):
    from pymongo import ReturnDocument

    repo, collection = repository
    now = datetime.now(timezone.utc)
    location = GeoLocation(latitude=26.0, longitude=85.0)
    document = make_mongo_document(
        sample_team,
        current_location=location.model_dump(mode="json"),
        last_location_update=now.isoformat(),
        updated_at=now.isoformat(),
        status=TeamStatus.UNKNOWN.value,
        availability_confirmed=False,
    )
    collection.find_one_and_update = AsyncMock(return_value=document)

    result = await repo.update_location(
        sample_team.team_id,
        current_location=location,
        updated_at=now,
    )

    collection.find_one_and_update.assert_awaited_once_with(
        {"_id": sample_team.team_id},
        {
            "$set": {
                "current_location": location.model_dump(mode="json"),
                "last_location_update": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    assert result is not None
    assert result.team_id == sample_team.team_id
    assert result.current_location == location
    assert result.last_location_update == now
    assert result.status == TeamStatus.UNKNOWN
    assert result.availability_confirmed is False


@pytest.mark.asyncio
async def test_update_location_returns_none_for_missing_team(repository):
    repo, collection = repository
    collection.find_one_and_update = AsyncMock(return_value=None)

    result = await repo.update_location(
        "missing-team",
        current_location=GeoLocation(latitude=26.0, longitude=85.0),
        updated_at=datetime.now(timezone.utc),
    )

    assert result is None
    collection.find_one_and_update.assert_awaited_once()
