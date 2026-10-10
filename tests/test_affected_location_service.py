"""Unit tests for the affected-location service."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.affected_location import AffectedLocation, SeverityLevel
from app.services.affected_location_service import AffectedLocationService


@pytest.fixture
def sample_location() -> AffectedLocation:
    now = datetime.now(timezone.utc)

    return AffectedLocation(
        location_id="location-service-001",
        event_id="event-service-001",
        location_name="Riverside settlement",
        state="Bihar",
        district="Patna",
        severity=SeverityLevel.UNKNOWN,
        assessed_at=now,
        last_changed_at=now,
        reassessment_required=True,
        reassessment_reason="Current conditions require reassessment.",
    )


@pytest.fixture
def service():
    repository = AsyncMock()
    flood_event_repository = AsyncMock()

    return AffectedLocationService(
        repository=repository,
        flood_event_repository=flood_event_repository,
    )


@pytest.mark.asyncio
async def test_create_location_when_event_exists(service, sample_location):
    service.flood_event_repository.get_by_id.return_value = object()
    service.repository.create.return_value = sample_location

    result = await service.create_location(sample_location)

    service.flood_event_repository.get_by_id.assert_awaited_once_with(
        sample_location.event_id
    )
    service.repository.create.assert_awaited_once_with(sample_location)
    assert result == sample_location


@pytest.mark.asyncio
async def test_create_location_when_event_does_not_exist(
    service,
    sample_location,
):
    service.flood_event_repository.get_by_id.return_value = None

    with pytest.raises(
        LookupError,
        match="Flood event 'event-service-001' does not exist.",
    ):
        await service.create_location(sample_location)

    service.repository.create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("event_id", ["", "   "])
async def test_create_location_rejects_empty_event_id(
    service,
    sample_location,
    event_id,
):
    sample_location.event_id = event_id

    with pytest.raises(ValueError, match="Event ID cannot be empty."):
        await service.create_location(sample_location)

    service.flood_event_repository.get_by_id.assert_not_awaited()
    service.repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_location_when_found(service, sample_location):
    service.repository.get_by_id.return_value = sample_location

    result = await service.get_location(sample_location.location_id)

    service.repository.get_by_id.assert_awaited_once_with(
        sample_location.location_id
    )
    assert result == sample_location


@pytest.mark.asyncio
async def test_get_location_when_missing(service):
    service.repository.get_by_id.return_value = None

    result = await service.get_location("missing-location")

    assert result is None
    service.repository.get_by_id.assert_awaited_once_with(
        "missing-location"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("location_id", ["", "   "])
async def test_get_location_rejects_empty_id(service, location_id):
    with pytest.raises(ValueError, match="Location ID cannot be empty."):
        await service.get_location(location_id)

    service.repository.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_locations_for_existing_event(service, sample_location):
    service.flood_event_repository.get_by_id.return_value = object()
    service.repository.list_by_event.return_value = [sample_location]

    result = await service.list_locations_for_event(
        sample_location.event_id,
        limit=10,
        skip=5,
    )

    service.flood_event_repository.get_by_id.assert_awaited_once_with(
        sample_location.event_id
    )
    service.repository.list_by_event.assert_awaited_once_with(
        sample_location.event_id,
        limit=10,
        skip=5,
    )
    assert result == [sample_location]


@pytest.mark.asyncio
async def test_list_locations_for_missing_event(service):
    service.flood_event_repository.get_by_id.return_value = None

    with pytest.raises(
        LookupError,
        match="Flood event 'missing-event' does not exist.",
    ):
        await service.list_locations_for_event("missing-event")

    service.repository.list_by_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_locations_rejects_empty_event_id(service):
    with pytest.raises(ValueError, match="Event ID cannot be empty."):
        await service.list_locations_for_event("   ")

    service.flood_event_repository.get_by_id.assert_not_awaited()
    service.repository.list_by_event.assert_not_awaited()
