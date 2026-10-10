from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from app.models.enums import EventStatus, EventVerificationStatus, HazardType
from app.models.flood_event import FloodEvent
from app.repositories.flood_event_repository import FloodEventRepository


@pytest.fixture
def sample_event():
    return FloodEvent(
        event_id="flood-test-001",
        hazard_type=HazardType.FLOOD,
        title="Flooding in test village",
        description="Floodwater has affected several houses.",
        location_name="Test Village",
        state="Karnataka",
        district="Bengaluru Urban",
        status=EventStatus.CANDIDATE,
        verification_status=EventVerificationStatus.UNVERIFIED,
        created_at=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_database():
    database = MagicMock()
    collection = MagicMock()

    database.__getitem__.return_value = collection

    collection.insert_one = AsyncMock()
    collection.find_one = AsyncMock()
    collection.find.return_value = MagicMock()

    return database, collection


@pytest.mark.asyncio
async def test_create_flood_event(mock_database, sample_event):
    database, collection = mock_database
    repository = FloodEventRepository(database)

    result = await repository.create(sample_event)

    assert result == sample_event
    collection.insert_one.assert_awaited_once()

    saved_document = collection.insert_one.await_args.args[0]

    assert saved_document["_id"] == "flood-test-001"
    assert "event_id" not in saved_document
    assert saved_document["title"] == "Flooding in test village"


@pytest.mark.asyncio
async def test_create_rejects_duplicate_event_id(
    mock_database, sample_event
):
    database, collection = mock_database
    repository = FloodEventRepository(database)

    collection.insert_one.side_effect = DuplicateKeyError("Duplicate key")

    with pytest.raises(ValueError, match="already exists"):
        await repository.create(sample_event)


@pytest.mark.asyncio
async def test_get_by_id_returns_event(mock_database, sample_event):
    database, collection = mock_database
    repository = FloodEventRepository(database)

    stored_document = sample_event.model_dump(mode="json")
    stored_document["_id"] = stored_document.pop("event_id")
    collection.find_one.return_value = stored_document

    result = await repository.get_by_id("flood-test-001")

    assert result == sample_event
    collection.find_one.assert_awaited_once_with(
        {"_id": "flood-test-001"}
    )


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_missing(mock_database):
    database, collection = mock_database
    repository = FloodEventRepository(database)

    collection.find_one.return_value = None

    result = await repository.get_by_id("missing-event")

    assert result is None


@pytest.mark.asyncio
async def test_list_events_returns_events(mock_database, sample_event):
    database, collection = mock_database
    repository = FloodEventRepository(database)

    stored_document = sample_event.model_dump(mode="json")
    stored_document["_id"] = stored_document.pop("event_id")

    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[stored_document])

    collection.find.return_value = cursor

    result = await repository.list_events(limit=20, skip=0)

    assert result == [sample_event]
    collection.find.assert_called_once_with({})
    cursor.sort.assert_called_once_with("created_at", -1)
    cursor.skip.assert_called_once_with(0)
    cursor.limit.assert_called_once_with(20)
    cursor.to_list.assert_awaited_once_with(length=20)


@pytest.mark.asyncio
async def test_list_events_rejects_invalid_limit(mock_database):
    database, _ = mock_database
    repository = FloodEventRepository(database)

    with pytest.raises(ValueError, match="limit"):
        await repository.list_events(limit=101)


@pytest.mark.asyncio
async def test_list_events_rejects_negative_skip(mock_database):
    database, _ = mock_database
    repository = FloodEventRepository(database)

    with pytest.raises(ValueError, match="skip"):
        await repository.list_events(skip=-1)