"""Unit tests for the resource-need service."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.resource_need import (
    NeedStatus,
    NeedType,
    NeedUrgency,
    ResourceNeed,
)
from app.services.resource_need_service import ResourceNeedService


@pytest.fixture
def sample_need():
    """Create a valid resource need."""

    now = datetime.now(timezone.utc)

    return ResourceNeed(
        need_id="need-test-001",
        event_id="event-test-001",
        location_id="location-test-001",
        need_type=NeedType.DRINKING_WATER,
        description="Drinking water required.",
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
def service():
    """Create a service with mocked repositories."""

    repository = AsyncMock()
    flood_event_repository = AsyncMock()

    return ResourceNeedService(
        repository=repository,
        flood_event_repository=flood_event_repository,
    )


@pytest.mark.asyncio
async def test_create_need_when_event_exists(service, sample_need):
    """A need is created when its flood event exists."""

    service.flood_event_repository.get_by_id.return_value = object()
    service.repository.create.return_value = sample_need

    result = await service.create_need(sample_need)

    service.flood_event_repository.get_by_id.assert_awaited_once_with(
        sample_need.event_id
    )
    service.repository.create.assert_awaited_once_with(sample_need)

    assert result == sample_need


@pytest.mark.asyncio
async def test_create_need_when_event_does_not_exist(
    service,
    sample_need,
):
    """A need cannot be created for a missing flood event."""

    service.flood_event_repository.get_by_id.return_value = None

    with pytest.raises(
        LookupError,
        match="Flood event 'event-test-001' does not exist.",
    ):
        await service.create_need(sample_need)

    service.repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_need_when_found(service, sample_need):
    """The service returns a need retrieved by ID."""

    service.repository.get_by_id.return_value = sample_need

    result = await service.get_need(sample_need.need_id)

    service.repository.get_by_id.assert_awaited_once_with(
        sample_need.need_id
    )
    assert result == sample_need


@pytest.mark.asyncio
async def test_get_need_when_missing(service):
    """The service returns None when the need is missing."""

    service.repository.get_by_id.return_value = None

    result = await service.get_need("missing-need")

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("need_id", ["", "   "])
async def test_get_need_rejects_empty_id(service, need_id):
    """Empty or whitespace-only need IDs are rejected."""

    with pytest.raises(ValueError, match="Need ID cannot be empty."):
        await service.get_need(need_id)

    service.repository.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_needs_for_existing_event(service, sample_need):
    """Needs are listed when the flood event exists."""

    service.flood_event_repository.get_by_id.return_value = object()
    service.repository.list_by_event.return_value = [sample_need]

    result = await service.list_needs_for_event(
        sample_need.event_id,
        limit=10,
        skip=5,
    )

    service.repository.list_by_event.assert_awaited_once_with(
        sample_need.event_id,
        limit=10,
        skip=5,
    )

    assert result == [sample_need]


@pytest.mark.asyncio
async def test_list_needs_for_missing_event(service):
    """Listing needs for a missing event raises LookupError."""

    service.flood_event_repository.get_by_id.return_value = None

    with pytest.raises(
        LookupError,
        match="Flood event 'missing-event' does not exist.",
    ):
        await service.list_needs_for_event("missing-event")

    service.repository.list_by_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_needs_rejects_empty_event_id(service):
    """Empty event IDs are rejected."""

    with pytest.raises(ValueError, match="Event ID cannot be empty."):
        await service.list_needs_for_event("   ")

    service.flood_event_repository.get_by_id.assert_not_awaited()
    service.repository.list_by_event.assert_not_awaited()