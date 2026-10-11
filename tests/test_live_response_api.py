from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.field_reports import get_live_response_service
from app.services.live_response_service import (
    LiveResponseConflict,
    LiveResponseNotFound,
)


@pytest.fixture
def live_response_service():
    service = AsyncMock()
    app.dependency_overrides[get_live_response_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_live_response_service, None)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def valid_report_payload():
    return {
        "team_id": "team-test-001",
        "report_type": "ROAD_BLOCKED",
        "title": "Road blocked near evacuation route",
        "description": "Field team reports a flooded road requiring assessment.",
        "location_name": "North evacuation road",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def test_submit_field_report_returns_created_response(
    client, live_response_service
):
    live_response_service.submit_report.return_value = {
        "report": {
            "report_id": "report-test-001",
            "event_id": "flood-test-001",
            "team_id": "team-test-001",
            "report_type": "ROAD_BLOCKED",
            "status": "RECEIVED",
        },
        "recommendation": {
            "recommendation_id": "recommendation-test-001",
            "status": "PROPOSED",
            "recommendation_type": "ROUTE_CHANGE",
        },
        "reassessment_requested": True,
        "dispatch_performed": False,
        "allocation_recalculated": False,
    }

    response = client.post(
        "/api/v1/flood-events/flood-test-001/field-reports",
        json=valid_report_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["report"]["report_id"] == "report-test-001"
    assert body["recommendation"]["status"] == "PROPOSED"
    assert body["reassessment_requested"] is True
    assert body["dispatch_performed"] is False
    assert body["allocation_recalculated"] is False

    live_response_service.submit_report.assert_awaited_once()


def test_submit_report_returns_404_for_missing_event_or_team(
    client, live_response_service
):
    live_response_service.submit_report.side_effect = LiveResponseNotFound(
        "Flood event not found."
    )

    response = client.post(
        "/api/v1/flood-events/missing-event/field-reports",
        json=valid_report_payload(),
    )

    assert response.status_code == 404
    assert "Flood event not found." in response.json()["detail"]


def test_submit_report_returns_409_for_unsupported_assignment(
    client, live_response_service
):
    live_response_service.submit_report.side_effect = LiveResponseConflict(
        "Assignment-linked reports are not supported."
    )

    payload = valid_report_payload()
    payload["assignment_id"] = "assignment-test-001"

    response = client.post(
        "/api/v1/flood-events/flood-test-001/field-reports",
        json=payload,
    )

    assert response.status_code == 409
    assert "Assignment-linked reports" in response.json()["detail"]


def test_submit_report_rejects_invalid_request(client, live_response_service):
    payload = valid_report_payload()
    payload["unexpected_field"] = "must not be accepted"

    response = client.post(
        "/api/v1/flood-events/flood-test-001/field-reports",
        json=payload,
    )

    assert response.status_code == 422
    live_response_service.submit_report.assert_not_awaited()


def test_submit_report_rejects_invalid_report_type(
    client, live_response_service
):
    payload = valid_report_payload()
    payload["report_type"] = "MADE_UP_REPORT_TYPE"

    response = client.post(
        "/api/v1/flood-events/flood-test-001/field-reports",
        json=payload,
    )

    assert response.status_code == 422
    live_response_service.submit_report.assert_not_awaited()


def test_list_field_reports_returns_service_results(
    client, live_response_service
):
    live_response_service.list_reports.return_value = [
        {
            "report_id": "report-test-001",
            "event_id": "flood-test-001",
            "status": "RECEIVED",
        }
    ]

    response = client.get(
        "/api/v1/flood-events/flood-test-001/field-reports?limit=10&skip=0"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["report_id"] == "report-test-001"


def test_list_recommendations_returns_service_results(
    client, live_response_service
):
    live_response_service.list_recommendations.return_value = [
        {
            "recommendation_id": "recommendation-test-001",
            "event_id": "flood-test-001",
            "status": "PROPOSED",
        }
    ]

    response = client.get(
        "/api/v1/flood-events/flood-test-001/"
        "reallocation-recommendations?limit=10&skip=0"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "PROPOSED"


def test_list_reports_rejects_invalid_pagination(
    client, live_response_service
):
    response = client.get(
        "/api/v1/flood-events/flood-test-001/field-reports?limit=101"
    )

    assert response.status_code == 422
    live_response_service.list_reports.assert_not_awaited()
