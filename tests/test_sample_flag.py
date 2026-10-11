"""The is_sample flag is exposed in responses but cannot be set through the API."""

from unittest.mock import AsyncMock

from app.api.flood_events import get_flood_event_service
from app.main import app
from app.models.affected_location import AffectedLocation
from app.models.flood_event import FloodEvent
from app.models.flood_observation import FloodObservation
from app.models.source import SourceRegistryEntry


def test_models_default_to_not_sample():
    assert FloodEvent(event_id="e1", title="Flood", location_name="Patna", state="Bihar").is_sample is False
    assert AffectedLocation(location_id="l1", event_id="e1", location_name="Patna", state="Bihar").is_sample is False
    assert FloodObservation.model_fields["is_sample"].default is False
    assert SourceRegistryEntry.model_fields["is_sample"].default is False


def test_create_flood_event_rejects_is_sample(client):
    service = AsyncMock()
    app.dependency_overrides[get_flood_event_service] = lambda: service

    response = client.post(
        "/api/v1/flood-events",
        json={"title": "Flood", "location_name": "Patna", "state": "Bihar", "is_sample": True},
    )

    assert response.status_code == 422
    service.create_event.assert_not_awaited()
