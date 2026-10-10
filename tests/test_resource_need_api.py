"""API tests for resource needs."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.api.resource_needs import get_resource_need_service
from app.main import app
from app.models.resource_need import (
    NeedStatus,
    NeedType,
    NeedUrgency,
    ResourceNeed,
)


@pytest.fixture
def sample_need():
    """Create a resource need for API tests."""

    now = datetime.now(timezone.utc)

    return ResourceNeed(
        need_id="need-api-test-001",
        event_id="event-api-test-001",
        location_id="location-api-test-001",
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
def mock_service(client):
    """Override the API service dependency with a mock."""

    service = AsyncMock()

    app.dependency_overrides[get_resource_need_service] = lambda: service

    yield service

    app.dependency_overrides.pop(get_resource_need_service, None)


def test_create_resource_need(client, mock_service, sample_need):
    """A valid resource-need request returns 201."""

    mock_service.create_need.return_value = sample_need

    payload = {
        "event_id": sample_need.event_id,
        "location_id": sample_need.location_id,
        "need_type": "DRINKING_WATER",
        "description": sample_need.description,
        "urgency": "HIGH",
        "quantity_requested": 100,
        "quantity_unit": "litres",
        "supporting_observation_ids": [],
    }

    response = client.post("/api/v1/resource-needs", json=payload)

    assert response.status_code == 201

    body = response.json()

    assert body["need_id"] == sample_need.need_id
    assert body["event_id"] == sample_need.event_id
    assert body["status"] == "REPORTED"

    created_need = mock_service.create_need.await_args.args[0]

    assert created_need.event_id == sample_need.event_id
    assert created_need.status == NeedStatus.REPORTED
    assert created_need.need_id != ""


def test_create_resource_need_for_missing_event(
    client,
    mock_service,
):
    """A missing flood event produces a 404 response."""

    mock_service.create_need.side_effect = LookupError(
        "Flood event 'missing-event' does not exist."
    )

    payload = {
        "event_id": "missing-event",
        "location_id": "location-api-test-001",
        "need_type": "DRINKING_WATER",
        "description": "Drinking water required.",
    }

    response = client.post("/api/v1/resource-needs", json=payload)

    assert response.status_code == 404
    assert "does not exist" in response.json()["detail"]


def test_create_resource_need_rejects_invalid_input(
    client,
    mock_service,
):
    """Invalid request data produces a 422 response."""

    payload = {
        "event_id": "event-api-test-001",
        "location_id": "location-api-test-001",
        "need_type": "INVALID_NEED_TYPE",
        "description": "Drinking water required.",
    }

    response = client.post("/api/v1/resource-needs", json=payload)

    assert response.status_code == 422
    mock_service.create_need.assert_not_awaited()


def test_get_resource_need(client, mock_service, sample_need):
    """An existing resource need returns 200."""

    mock_service.get_need.return_value = sample_need

    response = client.get(
        f"/api/v1/resource-needs/{sample_need.need_id}"
    )

    assert response.status_code == 200
    assert response.json()["need_id"] == sample_need.need_id
    assert response.json()["need_type"] == "DRINKING_WATER"

    mock_service.get_need.assert_awaited_once_with(sample_need.need_id)


def test_get_missing_resource_need(client, mock_service):
    """A missing resource need returns 404."""

    mock_service.get_need.return_value = None

    response = client.get("/api/v1/resource-needs/missing-need")

    assert response.status_code == 404


def test_list_resource_needs(client, mock_service, sample_need):
    """Resource needs can be listed for a flood event."""

    mock_service.list_needs_for_event.return_value = [sample_need]

    response = client.get(
        f"/api/v1/flood-events/{sample_need.event_id}/resource-needs",
        params={"limit": 10, "skip": 0},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["need_id"] == sample_need.need_id

    mock_service.list_needs_for_event.assert_awaited_once_with(
        sample_need.event_id,
        limit=10,
        skip=0,
    )


def test_list_resource_needs_for_missing_event(
    client,
    mock_service,
):
    """A missing flood event returns 404."""

    mock_service.list_needs_for_event.side_effect = LookupError(
        "Flood event 'missing-event' does not exist."
    )

    response = client.get(
        "/api/v1/flood-events/missing-event/resource-needs"
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
def test_list_resource_needs_rejects_invalid_pagination(
    client,
    mock_service,
    limit,
    skip,
):
    """Invalid pagination parameters produce a 422 response."""

    response = client.get(
        "/api/v1/flood-events/event-api-test-001/resource-needs",
        params={"limit": limit, "skip": skip},
    )

    assert response.status_code == 422
    mock_service.list_needs_for_event.assert_not_awaited()