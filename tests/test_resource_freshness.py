"""Tests for server-side check-in freshness and eligibility on resources."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.api.resource_inventory import get_resource_inventory_service
from app.api.response_teams import get_response_team_service
from app.main import app
from app.models.resource_inventory import InventoryStatus, ResourceInventory, ResourceType
from app.models.response_team import ResponseTeam, TeamCapability, TeamStatus
from app.services.resource_freshness import (
    FRESHNESS_RULE,
    ResourceFreshness,
    classify_freshness,
    inventory_status_fields,
    team_status_fields,
)

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
DAY = timedelta(hours=24)
F = ResourceFreshness


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(hours=0), F.FRESH),
        (timedelta(hours=17, minutes=59), F.FRESH),
        (timedelta(hours=18), F.DUE),
        (timedelta(hours=23, minutes=59), F.DUE),
        (timedelta(hours=24), F.STALE),
        (timedelta(hours=-1), F.UNVERIFIED),
    ],
)
def test_classify_freshness(age, expected):
    freshness, due_at = classify_freshness(NOW - age, DAY, NOW)

    assert freshness == expected
    assert due_at == NOW - age + DAY


def test_missing_check_in_is_unverified_with_no_due_time():
    assert classify_freshness(None, DAY, NOW) == (F.UNVERIFIED, None)


def make_inventory(**overrides):
    data = dict(
        inventory_id="inv-1",
        organisation_id="org-1",
        resource_type=ResourceType.BOATS,
        resource_name="Rescue boat",
        quantity_total=2,
        quantity_unit="boats",
        storage_location="Depot",
        status=InventoryStatus.AVAILABLE,
        availability_confirmed=True,
        last_verified_at=NOW - timedelta(hours=2),
    )
    return ResourceInventory(**{**data, **overrides})


def make_team(**overrides):
    data = dict(
        team_id="team-1",
        organisation_id="org-1",
        team_name="Boat crew",
        capabilities=[TeamCapability.BOAT_OPERATIONS],
        personnel_count=4,
        status=TeamStatus.AVAILABLE,
        availability_confirmed=True,
        last_status_update=NOW - timedelta(minutes=20),
    )
    return ResponseTeam(**{**data, **overrides})


def test_fresh_confirmed_inventory_is_eligible():
    fields = inventory_status_fields(make_inventory(), NOW)

    assert fields.freshness == F.FRESH
    assert fields.check_in_due_at == NOW + timedelta(hours=22)
    assert fields.check_in_interval_hours == 24
    assert fields.freshness_rule == FRESHNESS_RULE
    assert fields.eligible_for_allocation is True
    assert fields.status_reason is None


def test_stale_inventory_is_ineligible_with_reason():
    fields = inventory_status_fields(
        make_inventory(last_verified_at=NOW - timedelta(hours=30)), NOW
    )

    assert fields.freshness == F.STALE
    assert fields.eligible_for_allocation is False
    assert "too old" in fields.status_reason


def test_unverified_inventory_lists_every_reason():
    fields = inventory_status_fields(
        make_inventory(
            status=InventoryStatus.UNKNOWN,
            availability_confirmed=False,
            last_verified_at=None,
            quantity_reserved=2,
        ),
        NOW,
    )

    assert fields.freshness == F.UNVERIFIED
    assert fields.check_in_due_at is None
    for fragment in ("not AVAILABLE", "not been confirmed", "missing", "No unreserved"):
        assert fragment in fields.status_reason


def test_team_uses_two_hour_interval():
    due = team_status_fields(make_team(last_status_update=NOW - timedelta(minutes=95)), NOW)
    assigned = team_status_fields(make_team(current_assignment_id="a-1"), NOW)

    assert due.check_in_interval_hours == 2
    assert due.freshness == F.DUE
    assert due.eligible_for_allocation is True
    assert assigned.freshness == F.FRESH
    assert assigned.eligible_for_allocation is False
    assert assigned.status_reason == "Already has an assignment."


def test_inventory_api_includes_derived_fields(client):
    service = AsyncMock()
    service.get_inventory.return_value = make_inventory(last_verified_at=None, availability_confirmed=False)
    service.list_inventory.return_value = [make_inventory(last_verified_at=None, availability_confirmed=False)]
    app.dependency_overrides[get_resource_inventory_service] = lambda: service

    for body in (
        client.get("/api/v1/resource-inventory/inv-1").json(),
        client.get("/api/v1/organisations/org-1/resource-inventory").json()[0],
    ):
        assert body["freshness"] == "UNVERIFIED"
        assert body["check_in_due_at"] is None
        assert body["check_in_interval_hours"] == 24
        assert body["freshness_rule"] == FRESHNESS_RULE
        assert body["eligible_for_allocation"] is False
        assert body["status_reason"]
        assert body["is_sample"] is False


def test_team_api_includes_derived_fields(client):
    team = make_team(last_status_update=datetime.now(timezone.utc))
    service = AsyncMock()
    service.get_team.return_value = team
    app.dependency_overrides[get_response_team_service] = lambda: service

    body = client.get("/api/v1/response-teams/team-1").json()

    assert body["freshness"] == "FRESH"
    assert body["check_in_interval_hours"] == 2
    assert body["eligible_for_allocation"] is True
    assert body["status_reason"] is None
