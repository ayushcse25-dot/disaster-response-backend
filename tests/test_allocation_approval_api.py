"""API-level tests for allocation approval and rejection."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.api.allocation_plans import get_allocation_approval_service
from app.main import app
from app.services.allocation_approval_service import (
    ApprovalConflict,
    ApprovalNotFound,
    ApprovalServiceUnavailable,
    ApprovalValidationError,
)


@pytest.fixture
def approval_service(client):
    service = AsyncMock()
    app.dependency_overrides[get_allocation_approval_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_allocation_approval_service, None)


def result_record(status_value="APPROVED"):
    now = datetime.now(timezone.utc)
    return {
        "plan_id": "plan-phase3",
        "event_id": "event-phase3",
        "plan": {
            "event_id": "event-phase3",
            "generated_at": now.isoformat(),
            "algorithm_version": "1.0.0",
            "status": "READY",
            "blocked_reasons": [],
            "decisions": [],
            "unallocated_needs": [],
            "inventory_state_version": "sha256:test",
            "notes": ["Proposal only."],
        },
        "approval_status": status_value,
        "approved_by": "operator-1" if status_value == "APPROVED" else None,
        "approved_at": now.isoformat() if status_value == "APPROVED" else None,
        "rejected_by": "operator-1" if status_value == "REJECTED" else None,
        "rejected_at": now.isoformat() if status_value == "REJECTED" else None,
        "rejection_reason": "Insufficient field confirmation" if status_value == "REJECTED" else None,
        "created_at": now.isoformat(),
    }


def request_body():
    return {
        "actor_id": "operator-1",
        "actor_type": "HUMAN_OPERATOR",
        "reason": "Reviewed against current operational information.",
    }


def test_approve_endpoint_returns_approved_plan(client, approval_service):
    approval_service.approve.return_value = result_record("APPROVED")
    response = client.post(
        "/api/v1/allocation-plans/plan-phase3/approve", json=request_body()
    )
    assert response.status_code == 200
    assert response.json()["approval_status"] == "APPROVED"
    approval_service.approve.assert_awaited_once_with(
        "plan-phase3", actor_id="operator-1", actor_type="HUMAN_OPERATOR",
        reason="Reviewed against current operational information.",
    )


def test_reject_endpoint_returns_rejected_plan(client, approval_service):
    approval_service.reject.return_value = result_record("REJECTED")
    response = client.post(
        "/api/v1/allocation-plans/plan-phase3/reject", json=request_body()
    )
    assert response.status_code == 200
    assert response.json()["approval_status"] == "REJECTED"
    assert response.json()["rejection_reason"] == "Insufficient field confirmation"


@pytest.mark.parametrize(
    ("exception", "expected_status"),
    [
        (ApprovalNotFound("missing"), 404),
        (ApprovalConflict("already decided"), 409),
        (ApprovalValidationError("invalid proposal"), 422),
        (ApprovalServiceUnavailable("database error"), 503),
    ],
)
def test_approve_endpoint_maps_service_errors(
    client, approval_service, exception, expected_status
):
    approval_service.approve.side_effect = exception
    response = client.post(
        "/api/v1/allocation-plans/plan-phase3/approve", json=request_body()
    )
    assert response.status_code == expected_status


def test_reject_endpoint_maps_duplicate_decision_to_conflict(client, approval_service):
    approval_service.reject.side_effect = ApprovalConflict("already decided")
    response = client.post(
        "/api/v1/allocation-plans/plan-phase3/reject", json=request_body()
    )
    assert response.status_code == 409


def test_decision_endpoints_reject_missing_reason(client, approval_service):
    body = request_body()
    body["reason"] = ""
    response = client.post(
        "/api/v1/allocation-plans/plan-phase3/approve", json=body
    )
    assert response.status_code == 422
    approval_service.approve.assert_not_awaited()
