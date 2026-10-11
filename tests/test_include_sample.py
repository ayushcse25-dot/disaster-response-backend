"""include_sample=false must return only real (is_sample=false) records."""

import pytest

from app.models.flood_event import FloodEvent
from app.repositories.flood_event_repository import FloodEventRepository
from app.repositories.resource_inventory_repository import ResourceInventoryRepository


@pytest.mark.asyncio
async def test_include_sample_false_hides_sample_records(seeded_db):
    events = FloodEventRepository(seeded_db)
    await events.create(FloodEvent(event_id="real-1", title="Real flood", location_name="Patna",
                                   state="Bihar"))
    everything = await events.list_events(limit=100)
    real_only = await events.list_events(limit=100, include_sample=False)
    assert any(e.is_sample for e in everything)
    assert [e.event_id for e in real_only] == ["real-1"] and not real_only[0].is_sample
    assert await ResourceInventoryRepository(seeded_db).list_by_organisation(
        "sample-org-001", include_sample=False) == []


def test_flood_events_route_forwards_include_sample(client):
    from unittest.mock import AsyncMock

    from app.api.flood_events import get_flood_event_service
    from app.main import app

    service = AsyncMock()
    service.list_events.return_value = []
    service.severity_for_events.return_value = {}
    app.dependency_overrides[get_flood_event_service] = lambda: service
    assert client.get("/api/v1/flood-events?include_sample=false").status_code == 200
    service.list_events.assert_awaited_once_with(limit=20, skip=0, include_sample=False)
