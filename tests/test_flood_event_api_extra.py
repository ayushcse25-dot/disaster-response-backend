"""Additional API tests for flood event endpoints."""

from unittest.mock import AsyncMock

import pytest

from app.api.flood_events import get_flood_event_service
from app.main import app
from app.models.flood_event import FloodEvent


@pytest.fixture
def flood_service_for_api_tests(client):
    """Override the flood event service with an isolated mock."""
    service = AsyncMock()
    service.severity_for_events.return_value = {}
    app.dependency_overrides[get_flood_event_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_flood_event_service, None)


@pytest.fixture
def valid_flood_payload():
    """Return a valid flood event creation request."""
    return {
        "hazard_type": "FLOOD",
        "title": "Flooding in Patna",
        "description": "Rising water levels reported near residential areas.",
        "location_name": "Patna",
        "state": "Bihar",
        "district": "Patna",
        "location": {
            "latitude": 25.5941,
            "longitude": 85.1376,
        },
    }


@pytest.fixture
def sample_flood_event(valid_flood_payload):
    """Return a valid flood event model for mocked responses."""
    return FloodEvent(
        event_id="flood-api-test-001",
        **valid_flood_payload,
    )


def test_create_flood_event_returns_created_response(
    client,
    flood_service_for_api_tests,
    valid_flood_payload,
    sample_flood_event,
):
    flood_service_for_api_tests.create_event.return_value = sample_flood_event

    response = client.post(
        "/api/v1/flood-events",
        json=valid_flood_payload,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["event_id"] == "flood-api-test-001"
    assert body["title"] == valid_flood_payload["title"]
    assert body["hazard_type"] == "FLOOD"
    assert body["status"] == "CANDIDATE"
    assert body["verification_status"] == "UNVERIFIED"
    flood_service_for_api_tests.create_event.assert_awaited_once()


@pytest.mark.parametrize(
    "missing_field",
    ["title", "location_name", "state"],
)
def test_create_flood_event_rejects_missing_required_fields(
    client,
    flood_service_for_api_tests,
    valid_flood_payload,
    missing_field,
):
    payload = dict(valid_flood_payload)
    del payload[missing_field]

    response = client.post("/api/v1/flood-events", json=payload)

    assert response.status_code == 422
    flood_service_for_api_tests.create_event.assert_not_awaited()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "AB"),
        ("title", "T" * 201),
        ("description", "D" * 2001),
        ("location_name", ""),
        ("location_name", "L" * 201),
        ("state", ""),
        ("state", "S" * 101),
        ("district", "D" * 101),
    ],
)
def test_create_flood_event_rejects_invalid_text_lengths(
    client,
    flood_service_for_api_tests,
    valid_flood_payload,
    field,
    value,
):
    payload = dict(valid_flood_payload)
    payload[field] = value

    response = client.post("/api/v1/flood-events", json=payload)

    assert response.status_code == 422
    flood_service_for_api_tests.create_event.assert_not_awaited()


def test_create_flood_event_rejects_unknown_hazard_type(
    client,
    flood_service_for_api_tests,
    valid_flood_payload,
):
    payload = dict(valid_flood_payload)
    payload["hazard_type"] = "EARTHQUAKE"

    response = client.post("/api/v1/flood-events", json=payload)

    assert response.status_code == 422
    flood_service_for_api_tests.create_event.assert_not_awaited()


def test_create_flood_event_rejects_unexpected_fields(
    client,
    flood_service_for_api_tests,
    valid_flood_payload,
):
    payload = dict(valid_flood_payload)
    payload["event_id"] = "client-supplied-id"

    response = client.post("/api/v1/flood-events", json=payload)

    assert response.status_code == 422
    flood_service_for_api_tests.create_event.assert_not_awaited()


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (91, 0),
        (-91, 0),
        (0, 181),
        (0, -181),
    ],
)
def test_create_flood_event_rejects_out_of_range_coordinates(
    client,
    flood_service_for_api_tests,
    valid_flood_payload,
    latitude,
    longitude,
):
    payload = dict(valid_flood_payload)
    payload["location"] = {
        "latitude": latitude,
        "longitude": longitude,
    }

    response = client.post("/api/v1/flood-events", json=payload)

    assert response.status_code == 422
    flood_service_for_api_tests.create_event.assert_not_awaited()


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (90, 180),
        (-90, -180),
        (0, 0),
    ],
)
def test_create_flood_event_accepts_coordinate_boundaries(
    client,
    flood_service_for_api_tests,
    valid_flood_payload,
    latitude,
    longitude,
    sample_flood_event,
):
    payload = dict(valid_flood_payload)
    payload["location"] = {
        "latitude": latitude,
        "longitude": longitude,
    }
    flood_service_for_api_tests.create_event.return_value = sample_flood_event

    response = client.post("/api/v1/flood-events", json=payload)

    assert response.status_code == 201


def test_create_flood_event_accepts_missing_optional_location(
    client,
    flood_service_for_api_tests,
    valid_flood_payload,
    sample_flood_event,
):
    payload = dict(valid_flood_payload)
    payload["location"] = None
    flood_service_for_api_tests.create_event.return_value = sample_flood_event

    response = client.post("/api/v1/flood-events", json=payload)

    assert response.status_code == 201


def test_create_flood_event_maps_duplicate_conflict_to_409(
    client,
    flood_service_for_api_tests,
    valid_flood_payload,
):
    flood_service_for_api_tests.create_event.side_effect = ValueError(
        "Flood event already exists."
    )

    response = client.post(
        "/api/v1/flood-events",
        json=valid_flood_payload,
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_get_flood_event_returns_event(
    client,
    flood_service_for_api_tests,
    sample_flood_event,
):
    flood_service_for_api_tests.get_event.return_value = sample_flood_event

    response = client.get(
        "/api/v1/flood-events/flood-api-test-001"
    )

    assert response.status_code == 200
    assert response.json()["event_id"] == "flood-api-test-001"
    flood_service_for_api_tests.get_event.assert_awaited_once_with(
        "flood-api-test-001"
    )


def test_get_flood_event_returns_404_when_missing(
    client,
    flood_service_for_api_tests,
):
    flood_service_for_api_tests.get_event.return_value = None

    response = client.get(
        "/api/v1/flood-events/does-not-exist"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Flood event not found."


def test_list_flood_events_returns_events(
    client,
    flood_service_for_api_tests,
    sample_flood_event,
):
    flood_service_for_api_tests.list_events.return_value = [
        sample_flood_event
    ]

    response = client.get("/api/v1/flood-events")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["event_id"] == "flood-api-test-001"
    flood_service_for_api_tests.list_events.assert_awaited_once_with(
        limit=20,
        skip=0,
    )


def test_list_flood_events_returns_empty_list(
    client,
    flood_service_for_api_tests,
):
    flood_service_for_api_tests.list_events.return_value = []

    response = client.get("/api/v1/flood-events")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    ("limit", "skip"),
    [
        (0, 0),
        (101, 0),
        (1, -1),
    ],
)
def test_list_flood_events_rejects_invalid_pagination(
    client,
    flood_service_for_api_tests,
    limit,
    skip,
):
    response = client.get(
        "/api/v1/flood-events",
        params={"limit": limit, "skip": skip},
    )

    assert response.status_code == 422
    flood_service_for_api_tests.list_events.assert_not_awaited()


@pytest.mark.parametrize(
    ("limit", "skip"),
    [
        (1, 0),
        (100, 0),
        (20, 1000),
    ],
)
def test_list_flood_events_accepts_valid_pagination(
    client,
    flood_service_for_api_tests,
    limit,
    skip,
):
    flood_service_for_api_tests.list_events.return_value = []

    response = client.get(
        "/api/v1/flood-events",
        params={"limit": limit, "skip": skip},
    )

    assert response.status_code == 200
    flood_service_for_api_tests.list_events.assert_awaited_once_with(
        limit=limit,
        skip=skip,
    )
