"""API tests for persisted allocation plans."""

from app.exceptions import PlanningSnapshotError

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.api.allocation_plans import get_allocation_plan_service
from app.main import app
from app.models.allocation_plan import AllocationPlanRecord
from app.services.allocation_engine import AllocationPlan


@pytest.fixture
def allocation_plan_service_for_api_tests(client):
    service = AsyncMock()
    app.dependency_overrides[get_allocation_plan_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_allocation_plan_service, None)


@pytest.fixture
def sample_plan_record():
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    plan = AllocationPlan(
        event_id="event-api-001",
        generated_at=now,
        inventory_state_version="sha256:test-digest",
        status="READY",
        decisions=[],
        unallocated_needs=[],
        blocked_reasons=[],
        notes=["Planning proposal only."],
    )
    return AllocationPlanRecord(
        plan_id="plan-api-001",
        event_id="event-api-001",
        plan=plan,
        created_at=now,
    )


def test_generate_allocation_plan_returns_created_proposal(
    client, allocation_plan_service_for_api_tests, sample_plan_record
):
    allocation_plan_service_for_api_tests.generate_for_event.return_value = (
        sample_plan_record
    )

    response = client.post(
        "/api/v1/flood-events/event-api-001/allocation-plans"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["plan_id"] == "plan-api-001"
    assert body["event_id"] == "event-api-001"
    assert body["plan"]["status"] == "READY"
    assert body["plan"]["decisions"] == []
    allocation_plan_service_for_api_tests.generate_for_event.assert_awaited_once_with(
        "event-api-001"
    )


def test_generate_allocation_plan_returns_404_for_missing_event(
    client, allocation_plan_service_for_api_tests
):
    allocation_plan_service_for_api_tests.generate_for_event.side_effect = (
        LookupError("Flood event 'missing' does not exist.")
    )

    response = client.post("/api/v1/flood-events/missing/allocation-plans")

    assert response.status_code == 404


def test_generate_allocation_plan_returns_503_for_incomplete_snapshot(
    client, allocation_plan_service_for_api_tests
):
    allocation_plan_service_for_api_tests.generate_for_event.side_effect = (
        PlanningSnapshotError("snapshot limit")
    )

    response = client.post(
        "/api/v1/flood-events/event-api-001/allocation-plans"
    )

    assert response.status_code == 503
    assert "could not be loaded completely" in response.json()["detail"]


def test_list_allocation_plans_returns_records(
    client, allocation_plan_service_for_api_tests, sample_plan_record
):
    allocation_plan_service_for_api_tests.list_plans.return_value = [
        sample_plan_record
    ]

    response = client.get(
        "/api/v1/flood-events/event-api-001/allocation-plans",
        params={"limit": 10, "skip": 5},
    )

    assert response.status_code == 200
    assert [item["plan_id"] for item in response.json()] == ["plan-api-001"]
    allocation_plan_service_for_api_tests.list_plans.assert_awaited_once_with(
        "event-api-001", limit=10, skip=5
    )


def test_list_allocation_plans_returns_404_for_missing_event(
    client, allocation_plan_service_for_api_tests
):
    allocation_plan_service_for_api_tests.list_plans.side_effect = (
        LookupError("Flood event 'missing' does not exist.")
    )

    response = client.get("/api/v1/flood-events/missing/allocation-plans")

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("limit", "skip"),
    [(0, 0), (101, 0), (20, -1)],
)
def test_list_allocation_plans_rejects_invalid_pagination(
    client, allocation_plan_service_for_api_tests, limit, skip
):
    response = client.get(
        "/api/v1/flood-events/event-api-001/allocation-plans",
        params={"limit": limit, "skip": skip},
    )

    assert response.status_code == 422
    allocation_plan_service_for_api_tests.list_plans.assert_not_awaited()


def test_get_allocation_plan_returns_record(
    client, allocation_plan_service_for_api_tests, sample_plan_record
):
    allocation_plan_service_for_api_tests.get_plan.return_value = (
        sample_plan_record
    )

    response = client.get("/api/v1/allocation-plans/plan-api-001")

    assert response.status_code == 200
    assert response.json()["plan_id"] == "plan-api-001"
    allocation_plan_service_for_api_tests.get_plan.assert_awaited_once_with(
        "plan-api-001"
    )


def test_get_allocation_plan_returns_404_when_missing(
    client, allocation_plan_service_for_api_tests
):
    allocation_plan_service_for_api_tests.get_plan.return_value = None

    response = client.get("/api/v1/allocation-plans/does-not-exist")

    assert response.status_code == 404
