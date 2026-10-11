from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.enums import EventStatus, EventVerificationStatus, HazardType
from app.models.flood_event import FloodEvent
from app.repositories.flood_event_repository import FloodEventRepository
from app.services.flood_event_service import FloodEventService


@pytest.fixture
def sample_event():
    return FloodEvent(
        event_id="flood-service-test-001",
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
def mock_repository():
    repository = AsyncMock(spec=FloodEventRepository)
    return repository


@pytest.mark.asyncio
async def test_create_event(mock_repository, sample_event):
    mock_repository.create.return_value = sample_event
    service = FloodEventService(mock_repository)

    result = await service.create_event(sample_event)

    assert result == sample_event
    mock_repository.create.assert_awaited_once_with(sample_event)


@pytest.mark.asyncio
async def test_get_event(mock_repository, sample_event):
    mock_repository.get_by_id.return_value = sample_event
    service = FloodEventService(mock_repository)

    result = await service.get_event("flood-service-test-001")

    assert result == sample_event
    mock_repository.get_by_id.assert_awaited_once_with(
        "flood-service-test-001"
    )


@pytest.mark.asyncio
async def test_get_event_rejects_empty_id(mock_repository):
    service = FloodEventService(mock_repository)

    with pytest.raises(ValueError, match="Event ID cannot be empty"):
        await service.get_event("   ")

    mock_repository.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_event_returns_none_when_missing(mock_repository):
    mock_repository.get_by_id.return_value = None
    service = FloodEventService(mock_repository)

    result = await service.get_event("missing-event")

    assert result is None


@pytest.mark.asyncio
async def test_list_events(mock_repository, sample_event):
    mock_repository.list_events.return_value = [sample_event]
    service = FloodEventService(mock_repository)

    result = await service.list_events(limit=10, skip=0)

    assert result == [sample_event]
    mock_repository.list_events.assert_awaited_once_with(
        limit=10,
        skip=0, include_sample=True,
    )