from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.response_teams import get_response_team_service
from app.main import app
from app.models.flood_event import GeoLocation
from app.models.response_team import ResponseTeam, TeamStatus


@pytest.fixture
def client_and_service():
    service = AsyncMock()
    app.dependency_overrides[get_response_team_service] = lambda: service

    with TestClient(app) as client:
        yield client, service

    app.dependency_overrides.pop(get_response_team_service, None)


def make_team(**overrides):
    values = {
        "team_id": "team-status-001",
        "organisation_id": "organisation-001",
        "team_name": "Flood Response Team",
        "personnel_count": 6,
    }
    values.update(overrides)
    return ResponseTeam(**values)


def test_status_update_requires_confirmation_for_available(client_and_service):
    client, service = client_and_service

    response = client.patch(
        "/api/v1/response-teams/team-status-001/status",
        json={"status": "AVAILABLE", "availability_confirmed": False},
    )

    assert response.status_code == 422
    service.update_team_status.assert_not_awaited()


@pytest.mark.parametrize("status_value", ["UNKNOWN", "UNAVAILABLE", "OFFLINE"])
def test_non_operational_status_cannot_be_confirmed(
    client_and_service,
    status_value,
):
    client, service = client_and_service

    response = client.patch(
        "/api/v1/response-teams/team-status-001/status",
        json={"status": status_value, "availability_confirmed": True},
    )

    assert response.status_code == 422
    service.update_team_status.assert_not_awaited()


@pytest.mark.parametrize("status_value", ["ASSIGNED", "DEPLOYED"])
def test_status_update_cannot_bypass_assignment_workflow(
    client_and_service,
    status_value,
):
    client, service = client_and_service

    response = client.patch(
        "/api/v1/response-teams/team-status-001/status",
        json={"status": status_value, "availability_confirmed": False},
    )

    assert response.status_code == 422
    service.update_team_status.assert_not_awaited()


def test_status_update_accepts_explicit_available_confirmation(client_and_service):
    client, service = client_and_service
    service.update_team_status.return_value = make_team(
        status=TeamStatus.AVAILABLE,
        availability_confirmed=True,
    )

    response = client.patch(
        "/api/v1/response-teams/team-status-001/status",
        json={"status": "AVAILABLE", "availability_confirmed": True},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "AVAILABLE"
    assert response.json()["availability_confirmed"] is True
    service.update_team_status.assert_awaited_once()


def test_status_update_returns_404_for_missing_team(client_and_service):
    client, service = client_and_service
    service.update_team_status.return_value = None

    response = client.patch(
        "/api/v1/response-teams/missing-team/status",
        json={"status": "UNAVAILABLE", "availability_confirmed": False},
    )

    assert response.status_code == 404


def test_status_update_rejects_client_timestamp(client_and_service):
    client, service = client_and_service

    response = client.patch(
        "/api/v1/response-teams/team-status-001/status",
        json={
            "status": "AVAILABLE",
            "availability_confirmed": True,
            "last_status_update": "2026-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 422
    service.update_team_status.assert_not_awaited()


def test_location_update_does_not_accept_status_fields(client_and_service):
    client, service = client_and_service

    response = client.patch(
        "/api/v1/response-teams/team-status-001/location",
        json={
            "current_location": {"latitude": 26.0, "longitude": 85.0},
            "status": "AVAILABLE",
            "availability_confirmed": True,
        },
    )

    assert response.status_code == 422
    service.update_team_location.assert_not_awaited()


def test_location_update_preserves_unconfirmed_availability(client_and_service):
    client, service = client_and_service
    service.update_team_location.return_value = make_team(
        current_location=GeoLocation(latitude=26.0, longitude=85.0),
        status=TeamStatus.UNKNOWN,
        availability_confirmed=False,
    )

    response = client.patch(
        "/api/v1/response-teams/team-status-001/location",
        json={
            "current_location": {"latitude": 26.0, "longitude": 85.0},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "UNKNOWN"
    assert response.json()["availability_confirmed"] is False
    service.update_team_location.assert_awaited_once()
    call_kwargs = service.update_team_location.await_args.kwargs
    assert call_kwargs["current_location"] == GeoLocation(
        latitude=26.0,
        longitude=85.0,
    )


def test_location_update_returns_404_for_missing_team(client_and_service):
    client, service = client_and_service
    service.update_team_location.return_value = None

    response = client.patch(
        "/api/v1/response-teams/missing-team/location",
        json={
            "current_location": {"latitude": 26.0, "longitude": 85.0},
        },
    )

    assert response.status_code == 404
