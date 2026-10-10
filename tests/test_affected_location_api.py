"""API tests for affected locations."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.api.affected_locations import get_affected_location_service
from app.main import app
from app.models.affected_location import AffectedLocation, SeverityLevel
from app.models.flood_event import GeoLocation


@pytest.fixture
def sample_location():
    """Create an affected location for API tests."""

    now = datetime.now(timezone.utc)

    return AffectedLocation(
        location_id="location-api-test-001",
        event_id="event-api-test-001",
        location_name="Village Relief Zone",
        state="Bihar",
        district="Patna",
        coordinates=GeoLocation(latitude=25.5941, longitude=85.1376),
        severity=SeverityLevel.HIGH,
        supporting_observation_ids=["observation-api-test-001"],
        assessed_at=now,
        last_changed_at=now,
        reassessment_required=True,
        reassessment_reason=None,
    )


@pytest.fixture
def mock_affected_location_service(client):
    """Override the affected-location service dependency."""

    service = AsyncMock()
    app.dependency_overrides[get_affected_location_service] = (
        lambda: service
    )

    yield service

    app.dependency_overrides.pop(get_affected_location_service, None)


def test_create_affected_location(
    client,
    mock_affected_location_service,
    sample_location,
):
    """A valid request returns 201 and server-managed defaults."""

    mock_affected_location_service.create_location.return_value = (
        sample_location
    )

    payload = {
        "event_id": sample_location.event_id,
        "location_name": sample_location.location_name,
        "state": sample_location.state,
        "district": sample_location.district,
        "coordinates": {
            "latitude": 25.5941,
            "longitude": 85.1376,
        },
        "severity": "HIGH",
        "supporting_observation_ids": [
            "observation-api-test-001"
        ],
    }

    response = client.post("/api/v1/affected-locations", json=payload)

    assert response.status_code == 201

    body = response.json()
    assert body["location_id"] == sample_location.location_id
    assert body["event_id"] == sample_location.event_id
    assert body["severity"] == "HIGH"
    assert body["reassessment_required"] is True

    created = (
        mock_affected_location_service.create_location.await_args.args[0]
    )
    assert created.location_id
    assert created.event_id == sample_location.event_id
    assert created.reassessment_required is True


def test_create_affected_location_for_missing_event(
    client,
    mock_affected_location_service,
):
    """A nonexistent flood event returns 404."""

    mock_affected_location_service.create_location.side_effect = LookupError(
        "Flood event 'missing-event' does not exist."
    )

    payload = {
        "event_id": "missing-event",
        "location_name": "Flooded village",
        "state": "Bihar",
    }

    response = client.post("/api/v1/affected-locations", json=payload)

    assert response.status_code == 404
    assert "does not exist" in response.json()["detail"]


def test_create_affected_location_rejects_invalid_input(
    client,
    mock_affected_location_service,
):
    """Invalid request data returns 422."""

    payload = {
        "event_id": "event-api-test-001",
        "location_name": "Flooded village",
        "state": "Bihar",
        "severity": "INVALID_SEVERITY",
    }

    response = client.post("/api/v1/affected-locations", json=payload)

    assert response.status_code == 422
    mock_affected_location_service.create_location.assert_not_awaited()


def test_create_affected_location_rejects_server_managed_fields(
    client,
    mock_affected_location_service,
):
    """Clients cannot set internal IDs or reassessment state."""

    payload = {
        "event_id": "event-api-test-001",
        "location_name": "Flooded village",
        "state": "Bihar",
        "location_id": "client-supplied-id",
        "reassessment_required": False,
    }

    response = client.post("/api/v1/affected-locations", json=payload)

    assert response.status_code == 422
    mock_affected_location_service.create_location.assert_not_awaited()


def test_get_affected_location(
    client,
    mock_affected_location_service,
    sample_location,
):
    """An existing affected location returns 200."""

    mock_affected_location_service.get_location.return_value = sample_location

    response = client.get(
        f"/api/v1/affected-locations/{sample_location.location_id}"
    )

    assert response.status_code == 200
    assert response.json()["location_id"] == sample_location.location_id
    assert response.json()["location_name"] == sample_location.location_name

    mock_affected_location_service.get_location.assert_awaited_once_with(
        sample_location.location_id
    )


def test_get_missing_affected_location(
    client,
    mock_affected_location_service,
):
    """A nonexistent affected location returns 404."""

    mock_affected_location_service.get_location.return_value = None

    response = client.get(
        "/api/v1/affected-locations/missing-location"
    )

    assert response.status_code == 404


def test_get_affected_location_rejects_blank_id(
    client,
    mock_affected_location_service,
):
    """A blank location ID is rejected by the service."""

    mock_affected_location_service.get_location.side_effect = ValueError(
        "Location ID must not be blank."
    )

    response = client.get("/api/v1/affected-locations/%20")

    assert response.status_code == 422


def test_list_affected_locations(
    client,
    mock_affected_location_service,
    sample_location,
):
    """Affected locations can be listed for a flood event."""

    mock_affected_location_service.list_locations_for_event.return_value = [
        sample_location
    ]

    response = client.get(
        f"/api/v1/flood-events/{sample_location.event_id}/affected-locations",
        params={"limit": 10, "skip": 0},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["location_id"] == sample_location.location_id

    mock_affected_location_service.list_locations_for_event.assert_awaited_once_with(
        sample_location.event_id,
        limit=10,
        skip=0,
    )


def test_list_affected_locations_for_missing_event(
    client,
    mock_affected_location_service,
):
    """A nonexistent flood event returns 404."""

    mock_affected_location_service.list_locations_for_event.side_effect = (
        LookupError("Flood event 'missing-event' does not exist.")
    )

    response = client.get(
        "/api/v1/flood-events/missing-event/affected-locations"
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("limit", "skip"),
    [
        (0, 0),
        (101, 0),
        (10, -1),
    ],
)
def test_list_affected_locations_rejects_invalid_pagination(
    client,
    mock_affected_location_service,
    limit,
    skip,
):
    """Invalid pagination parameters return 422."""

    response = client.get(
        "/api/v1/flood-events/event-api-test-001/affected-locations",
        params={"limit": limit, "skip": skip},
    )

    assert response.status_code == 422
    mock_affected_location_service.list_locations_for_event.assert_not_awaited()
