"""Unit tests for the affected-location repository."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from app.models.affected_location import AffectedLocation, SeverityLevel
from app.repositories.affected_location_repository import (
    AffectedLocationRepository,
)


@pytest.fixture
def sample_location() -> AffectedLocation:
    now = datetime.now(timezone.utc)

    return AffectedLocation(
        location_id="location-test-001",
        event_id="event-test-001",
        location_name="Riverside settlement",
        state="Bihar",
        district="Patna",
        severity=SeverityLevel.HIGH,
        assessed_at=now,
        last_changed_at=now,
        reassessment_required=True,
    )


@pytest.fixture
def repository():
    database = MagicMock()
    collection = MagicMock()
    collection.insert_one = AsyncMock()
    collection.find_one = AsyncMock()
    database.__getitem__.return_value = collection

    return AffectedLocationRepository(database), collection


@pytest.mark.asyncio
async def test_create_affected_location(repository, sample_location):
    repo, collection = repository

    result = await repo.create(sample_location)

    assert result == sample_location
    collection.insert_one.assert_awaited_once()

    document = collection.insert_one.await_args.args[0]
    assert document["_id"] == sample_location.location_id
    assert "location_id" not in document
    assert document["event_id"] == sample_location.event_id


@pytest.mark.asyncio
async def test_create_duplicate_location(repository, sample_location):
    repo, collection = repository
    collection.insert_one.side_effect = DuplicateKeyError("duplicate key")

    with pytest.raises(ValueError, match="already exists"):
        await repo.create(sample_location)


@pytest.mark.asyncio
async def test_get_existing_location(repository, sample_location):
    repo, collection = repository
    document = sample_location.model_dump(mode="json")
    document["_id"] = document.pop("location_id")
    collection.find_one.return_value = document

    result = await repo.get_by_id(sample_location.location_id)

    collection.find_one.assert_awaited_once_with(
        {"_id": sample_location.location_id}
    )
    assert result is not None
    assert result.location_id == sample_location.location_id
    assert result.event_id == sample_location.event_id
    assert result.severity == SeverityLevel.HIGH


@pytest.mark.asyncio
async def test_get_missing_location(repository):
    repo, collection = repository
    collection.find_one.return_value = None

    result = await repo.get_by_id("missing-location")

    assert result is None


@pytest.mark.asyncio
async def test_list_locations_by_event(repository, sample_location):
    repo, collection = repository
    document = sample_location.model_dump(mode="json")
    document["_id"] = document.pop("location_id")

    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[document])
    collection.find.return_value = cursor

    result = await repo.list_by_event(
        sample_location.event_id,
        limit=10,
        skip=5,
    )

    collection.find.assert_called_once_with(
        {"event_id": sample_location.event_id}
    )
    cursor.sort.assert_called_once_with("last_changed_at", -1)
    cursor.skip.assert_called_once_with(5)
    cursor.limit.assert_called_once_with(10)
    cursor.to_list.assert_awaited_once_with(length=10)

    assert len(result) == 1
    assert result[0].location_id == sample_location.location_id


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 101])
async def test_list_locations_rejects_invalid_limit(repository, limit):
    repo, _ = repository

    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        await repo.list_by_event("event-test-001", limit=limit)


@pytest.mark.asyncio
async def test_list_locations_rejects_negative_skip(repository):
    repo, _ = repository

    with pytest.raises(ValueError, match="skip cannot be negative"):
        await repo.list_by_event("event-test-001", skip=-1)


@pytest.mark.asyncio
async def test_list_locations_rejects_empty_event_id(repository):
    repo, _ = repository

    with pytest.raises(ValueError, match="Event ID cannot be empty"):
        await repo.list_by_event("   ")
