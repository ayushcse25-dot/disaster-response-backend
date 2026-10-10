"""MongoDB repository tests for allocation plans."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from app.models.allocation_plan import AllocationPlanRecord
from app.services.allocation_engine import AllocationPlan
from app.repositories.allocation_plan_repository import AllocationPlanRepository


@pytest.fixture
def sample_record():
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    plan = AllocationPlan(
        event_id="event-repo-001",
        generated_at=now,
        inventory_state_version="sha256:repository-test",
        status="READY",
        decisions=[],
        unallocated_needs=[],
        blocked_reasons=[],
        notes=["Proposal only."],
    )
    return AllocationPlanRecord(
        plan_id="plan-repo-001",
        event_id="event-repo-001",
        plan=plan,
        created_at=now,
    )


@pytest.fixture
def mock_collection():
    collection = MagicMock()
    collection.insert_one = AsyncMock()
    collection.find_one = AsyncMock()
    collection.find.return_value = MagicMock()
    return collection


@pytest.fixture
def repository(mock_collection):
    database = MagicMock()
    database.__getitem__.return_value = mock_collection
    return AllocationPlanRepository(database)


@pytest.mark.asyncio
async def test_create_serializes_record_and_uses_plan_id_as_mongo_id(
    repository, mock_collection, sample_record
):
    result = await repository.create(sample_record)

    assert result == sample_record
    mock_collection.insert_one.assert_awaited_once()
    document = mock_collection.insert_one.await_args.args[0]
    assert document["_id"] == "plan-repo-001"
    assert "plan_id" not in document
    assert document["event_id"] == "event-repo-001"
    assert document["plan"]["inventory_state_version"] == "sha256:repository-test"


@pytest.mark.asyncio
async def test_create_maps_duplicate_plan_id_to_value_error(
    repository, mock_collection, sample_record
):
    mock_collection.insert_one.side_effect = DuplicateKeyError("duplicate")

    with pytest.raises(ValueError, match="already exists"):
        await repository.create(sample_record)


@pytest.mark.asyncio
async def test_get_by_id_deserializes_record(
    repository, mock_collection, sample_record
):
    document = sample_record.model_dump(mode="json")
    document["_id"] = document.pop("plan_id")
    mock_collection.find_one.return_value = document

    result = await repository.get_by_id("plan-repo-001")

    assert result == sample_record
    mock_collection.find_one.assert_awaited_once_with(
        {"_id": "plan-repo-001"}
    )


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_missing(repository, mock_collection):
    mock_collection.find_one.return_value = None

    result = await repository.get_by_id("missing-plan")

    assert result is None


@pytest.mark.asyncio
async def test_list_by_event_sorts_and_applies_pagination(
    repository, mock_collection, sample_record
):
    document = sample_record.model_dump(mode="json")
    document["_id"] = document.pop("plan_id")

    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[document])
    mock_collection.find.return_value = cursor

    result = await repository.list_by_event(
        "event-repo-001", limit=10, skip=5
    )

    assert result == [sample_record]
    mock_collection.find.assert_called_once_with(
        {"event_id": "event-repo-001"}
    )
    cursor.sort.assert_called_once_with("created_at", -1)
    cursor.skip.assert_called_once_with(5)
    cursor.limit.assert_called_once_with(10)
    cursor.to_list.assert_awaited_once_with(length=10)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_id", "limit", "skip", "message"),
    [
        (" ", 20, 0, "Event ID"),
        ("event-1", 0, 0, "limit"),
        ("event-1", 101, 0, "limit"),
        ("event-1", 20, -1, "skip"),
    ],
)
async def test_list_by_event_rejects_invalid_arguments(
    repository, event_id, limit, skip, message
):
    with pytest.raises(ValueError, match=message):
        await repository.list_by_event(
            event_id, limit=limit, skip=skip
        )
