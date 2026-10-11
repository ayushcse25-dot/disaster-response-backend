"""Authentication, role and NGO scope tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.api.allocation_plans import get_allocation_plan_service, get_plan_lifecycle_service
from app.api.auth_deps import get_current_user
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.main import app
from app.models.allocation_plan import AllocationPlanRecord, AllocationPlanView
from app.models.user import AccountStatus, Principal, Role
from app.services import auth_service
from app.services.allocation_engine import AllocationPlan
from app.services.auth_service import AuthError


def test_password_hash_and_token_roundtrip():
    stored = hash_password("s3cret")
    assert verify_password("s3cret", stored) and not verify_password("nope", stored)
    token = create_token({"sub": "u1", "role": "WORKER"}, "k", 60)
    assert decode_token(token, "k")["sub"] == "u1"
    assert decode_token(token, "other-key") is None


def test_routes_require_a_token(client):
    app.dependency_overrides.pop(get_current_user)
    response = client.get("/api/v1/allocation-plans/any")
    assert response.status_code == 401 and response.json()["code"] == "UNAUTHENTICATED"


def test_ngo_cannot_read_another_ngos_plan(client):
    now = datetime.now(timezone.utc)
    record = AllocationPlanRecord(
        plan_id="p1", event_id="e1", ngo_id="ngo-a", created_at=now,
        plan=AllocationPlan(event_id="e1", generated_at=now, status="READY",
                            inventory_state_version="sha256:x"),
    )
    service, lifecycle = AsyncMock(), AsyncMock()
    service.get_plan.return_value = record
    lifecycle.view.side_effect = lambda r: AllocationPlanView(**r.model_dump())
    app.dependency_overrides[get_allocation_plan_service] = lambda: service
    app.dependency_overrides[get_plan_lifecycle_service] = lambda: lifecycle

    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="b", role=Role.NGO_ADMIN, display_name="B", ngo_id="ngo-b")
    response = client.get("/api/v1/allocation-plans/p1")
    assert response.status_code == 403 and response.json()["code"] == "NGO_SCOPE"

    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="a", role=Role.NGO_ADMIN, display_name="A", ngo_id="ngo-a")
    assert client.get("/api/v1/allocation-plans/p1").status_code == 200


@pytest.mark.asyncio
async def test_disabled_worker_is_rejected(seeded_db):
    worker, password = await auth_service.create_worker(seeded_db, "sample-org-001", "Ravi")
    assert (await auth_service.authenticate_worker(
        seeded_db, "riveraid", worker.worker_id, password)).user_id == worker.user_id

    await auth_service.set_worker_status(seeded_db, "sample-org-001", worker.worker_id,
                                         AccountStatus.DISABLED)
    with pytest.raises(AuthError) as err:
        await auth_service.authenticate_worker(seeded_db, "RIVERAID", worker.worker_id, password)
    assert err.value.code == "ACCOUNT_DISABLED"
    with pytest.raises(AuthError):
        await auth_service.load_active_principal(seeded_db, worker.user_id)
