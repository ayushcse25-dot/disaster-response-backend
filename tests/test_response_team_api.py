from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.response_teams import get_response_team_service
from app.main import app
from app.models.response_team import ResponseTeam, TeamCapability, TeamStatus


@pytest.fixture
def client_and_service():
    service = AsyncMock()

    app.dependency_overrides[get_response_team_service] = lambda: service

    with TestClient(app) as client:
        yield client, service

    app.dependency_overrides.pop(get_response_team_service, None)


def sample_team(**overrides) -> ResponseTeam:
    values = {
        "team_id": "team-test-001",
        "organisation_id": "organisation-test-001",
        "team_name": "Flood Rescue Team",
        "capabilities": [TeamCapability.WATER_RESCUE, TeamCapability.EVACUATION],
        "equipment": ["Rescue boat", "Life jackets"],
        "personnel_count": 8,
    }
    values.update(overrides)
    return ResponseTeam(**values)


def test_create_team_returns_created_team_and_safe_defaults(client_and_service):
    client, service = client_and_service
    service.create_team.return_value = sample_team(
        team_id="12345678-1234-5678-1234-567812345678"
    )

    response = client.post(
        "/api/v1/response-teams",
        json={
            "organisation_id": "organisation-test-001",
            "team_name": "Flood Rescue Team",
            "capabilities": ["WATER_RESCUE", "EVACUATION"],
            "equipment": ["Rescue boat", "Life jackets"],
            "personnel_count": 8,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["organisation_id"] == "organisation-test-001"
    assert body["team_name"] == "Flood Rescue Team"
    assert body["status"] == "UNKNOWN"
    assert body["availability_confirmed"] is False
    assert body["current_assignment_id"] is None
    UUID(body["team_id"])
    service.create_team.assert_awaited_once()


def test_create_team_rejects_client_supplied_id(client_and_service):
    client, service = client_and_service

    response = client.post(
        "/api/v1/response-teams",
        json={
            "team_id": "client-chosen-id",
            "organisation_id": "organisation-test-001",
            "team_name": "Flood Rescue Team",
            "personnel_count": 8,
        },
    )

    assert response.status_code == 422
    service.create_team.assert_not_awaited()


@pytest.mark.parametrize(
    "extra_fields",
    [
        {"status": "AVAILABLE"},
        {"availability_confirmed": True},
        {"current_assignment_id": "assignment-001"},
    ],
)
def test_create_team_rejects_client_controlled_operational_fields(
    client_and_service,
    extra_fields,
):
    client, service = client_and_service

    payload = {
        "organisation_id": "organisation-test-001",
        "team_name": "Flood Rescue Team",
        "personnel_count": 8,
        **extra_fields,
    }

    response = client.post("/api/v1/response-teams", json=payload)

    assert response.status_code == 422
    service.create_team.assert_not_awaited()


def test_create_team_rejects_invalid_payload(client_and_service):
    client, service = client_and_service

    response = client.post(
        "/api/v1/response-teams",
        json={
            "organisation_id": "organisation-test-001",
            "team_name": "X",
            "personnel_count": -1,
        },
    )

    assert response.status_code == 422
    service.create_team.assert_not_awaited()


def test_create_team_returns_conflict_for_duplicate_id(client_and_service):
    client, service = client_and_service
    service.create_team.side_effect = ValueError(
        "Response team already exists."
    )

    response = client.post(
        "/api/v1/response-teams",
        json={
            "organisation_id": "organisation-test-001",
            "team_name": "Flood Rescue Team",
            "personnel_count": 8,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Response team already exists."


def test_get_team_returns_team(client_and_service):
    client, service = client_and_service
    service.get_team.return_value = sample_team()

    response = client.get("/api/v1/response-teams/team-test-001")

    assert response.status_code == 200
    assert response.json()["team_id"] == "team-test-001"
    assert response.json()["availability_confirmed"] is False
    service.get_team.assert_awaited_once_with("team-test-001")


def test_get_team_returns_404_when_missing(client_and_service):
    client, service = client_and_service
    service.get_team.return_value = None

    response = client.get("/api/v1/response-teams/missing-team")

    assert response.status_code == 404


def test_get_team_returns_422_for_invalid_id(client_and_service):
    client, service = client_and_service
    service.get_team.side_effect = ValueError("Team ID cannot be empty.")

    response = client.get("/api/v1/response-teams/%20")

    assert response.status_code == 422


def test_list_teams_for_organisation(client_and_service):
    client, service = client_and_service
    service.list_teams_for_organisation.return_value = [
        sample_team(),
        sample_team(
            team_id="team-test-002",
            team_name="Medical Support Team",
            capabilities=[TeamCapability.MEDICAL_AID],
        ),
    ]

    response = client.get(
        "/api/v1/organisations/organisation-test-001/response-teams"
        "?limit=10&skip=0"
    )

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["team_id"] == "team-test-001"
    service.list_teams_for_organisation.assert_awaited_once_with(
        "organisation-test-001",
        limit=10,
        skip=0,
    )


def test_list_teams_returns_empty_list_when_none_registered(client_and_service):
    client, service = client_and_service
    service.list_teams_for_organisation.return_value = []

    response = client.get(
        "/api/v1/organisations/organisation-test-001/response-teams"
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "query",
    ["?limit=0", "?limit=101", "?skip=-1"],
)
def test_list_teams_rejects_invalid_pagination(client_and_service, query):
    client, service = client_and_service

    response = client.get(
        "/api/v1/organisations/organisation-test-001/response-teams" + query
    )

    assert response.status_code == 422
    service.list_teams_for_organisation.assert_not_awaited()


def test_list_teams_returns_422_for_blank_organisation_id(client_and_service):
    client, service = client_and_service
    service.list_teams_for_organisation.side_effect = ValueError(
        "Organisation ID cannot be empty."
    )

    response = client.get("/api/v1/organisations/%20/response-teams")

    assert response.status_code == 422
