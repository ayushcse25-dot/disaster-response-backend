"""Unit tests for the resource-need repository."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from app.models.resource_need import (
    NeedStatus,
    NeedType,
    NeedUrgency,
    ResourceNeed,
)
from app.repositories.resource_need_repository import ResourceNeedRepository


@pytest.fixture
def sample_need() -> ResourceNeed:
    """Create a valid resource need for testing."""

    now = datetime.now(timezone.utc)

    return ResourceNeed(
        need_id="need-test-001",
        event_id="event-test-001",
        location_id="location-test-001",
        need_type=NeedType.DRINKING_WATER,
        description="Drinking water required for affected families.",
        urgency=NeedUrgency.HIGH,
        status=NeedStatus.REPORTED,
        quantity_requested=100,
        quantity_unit="litres",
        quantity_fulfilled=0,
        supporting_observation_ids=[],
        reported_at=now,
        updated_at=now,
        reassessment_required=True,
    )


@pytest.fixture
def mock_database():
    """Create a mocked MongoDB database and collection."""

    database = MagicMock()
    collection = MagicMock()

    collection.insert_one = AsyncMock()
    collection.find_one = AsyncMock()

    database.__getitem__.return_value = collection

    return database, collection


@pytest.fixture
def repository(mock_database):
    """Create a repository using the mocked collection."""

    database, _ = mock_database
    return ResourceNeedRepository(database)


@pytest.mark.asyncio
async def test_create_resource_need(
    repository,
    mock_database,
    sample_need,
):
    """Creation stores the need ID as MongoDB's _id."""

    _, collection = mock_database

    result = await repository.create(sample_need)

    collection.insert_one.assert_awaited_once()

    document = collection.insert_one.await_args.args[0]

    assert document["_id"] == sample_need.need_id
    assert "need_id" not in document
    assert document["event_id"] == sample_need.event_id
    assert result == sample_need


@pytest.mark.asyncio
async def test_create_duplicate_need_id(
    repository,
    mock_database,
    sample_need,
):
    """Duplicate IDs are converted into ValueError."""

    _, collection = mock_database

    collection.insert_one.side_effect = DuplicateKeyError(
        "Duplicate resource-need ID"
    )

    with pytest.raises(
        ValueError,
        match="Resource need 'need-test-001' already exists.",
    ):
        await repository.create(sample_need)


@pytest.mark.asyncio
async def test_get_by_id_when_found(
    repository,
    mock_database,
    sample_need,
):
    """An existing resource need is returned correctly."""

    _, collection = mock_database

    document = sample_need.model_dump(mode="json")
    document["_id"] = document.pop("need_id")

    collection.find_one.return_value = document

    result = await repository.get_by_id(sample_need.need_id)

    collection.find_one.assert_awaited_once_with(
        {"_id": sample_need.need_id}
    )

    assert result is not None
    assert result.need_id == sample_need.need_id
    assert result.event_id == sample_need.event_id
    assert result.need_type == NeedType.DRINKING_WATER


@pytest.mark.asyncio
async def test_get_by_id_when_missing(
    repository,
    mock_database,
):
    """A missing resource need returns None."""

    _, collection = mock_database
    collection.find_one.return_value = None

    result = await repository.get_by_id("missing-need")

    assert result is None


@pytest.mark.asyncio
async def test_list_by_event(
    repository,
    mock_database,
    sample_need,
):
    """Needs are listed using the requested event and pagination."""

    _, collection = mock_database

    document = sample_need.model_dump(mode="json")
    document["_id"] = document.pop("need_id")

    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[document])

    collection.find.return_value = cursor

    result = await repository.list_by_event(
        sample_need.event_id,
        limit=10,
        skip=5,
    )

    collection.find.assert_called_once_with(
        {"event_id": sample_need.event_id}
    )
    cursor.sort.assert_called_once_with("reported_at", -1)
    cursor.skip.assert_called_once_with(5)
    cursor.limit.assert_called_once_with(10)
    cursor.to_list.assert_awaited_once_with(length=10)

    assert len(result) == 1
    assert result[0].need_id == sample_need.need_id


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 101])
async def test_list_by_event_rejects_invalid_limit(
    repository,
    limit,
):
    """Limits outside the range 1-100 are rejected."""

    with pytest.raises(
        ValueError,
        match="limit must be between 1 and 100.",
    ):
        await repository.list_by_event(
            "event-test-001",
            limit=limit,
        )


@pytest.mark.asyncio
async def test_list_by_event_rejects_negative_skip(repository):
    """Negative pagination offsets are rejected."""

    with pytest.raises(
        ValueError,
        match="skip cannot be negative.",
    ):
        await repository.list_by_event(
            "event-test-001",
            skip=-1,
        )