"""Tests for the server-side event severity rule."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.flood_events import get_flood_event_service
from app.main import app
from app.models.affected_location import SeverityLevel
from app.models.flood_event import FloodEvent
from app.repositories.affected_location_repository import AffectedLocationRepository
from app.services.event_severity import SEVERITY_RULE, derive_event_severity
from app.services.flood_event_service import FloodEventService

L = SeverityLevel


@pytest.mark.parametrize(
    ("levels", "expected"),
    [
        ([], L.UNKNOWN),
        ([L.UNKNOWN, L.UNKNOWN], L.UNKNOWN),
        ([L.LOW], L.LOW),
        ([L.LOW, L.MODERATE], L.MODERATE),
        ([L.UNKNOWN, L.HIGH, L.MODERATE], L.HIGH),
        ([L.CRITICAL, L.LOW, L.HIGH], L.CRITICAL),
    ],
)
def test_severity_is_highest_known_location_severity(levels, expected):
    assert derive_event_severity(levels).severity == expected


def test_severity_basis_counts_locations():
    result = derive_event_severity([L.UNKNOWN, L.HIGH, L.LOW])

    assert result.severity_basis.rule == SEVERITY_RULE
    assert result.severity_basis.location_count == 3
    assert result.severity_basis.assessed_location_count == 2


@pytest.mark.asyncio
async def test_repository_groups_severities_by_event():
    cursor = MagicMock()
    cursor.to_list = AsyncMock(
        return_value=[
            {"_id": "l1", "event_id": "e1", "severity": "HIGH"},
            {"_id": "l2", "event_id": "e1", "severity": "LOW"},
            {"_id": "l3", "event_id": "e2"},
        ]
    )
    collection = MagicMock()
    collection.find.return_value = cursor
    database = MagicMock()
    database.__getitem__.return_value = collection

    result = await AffectedLocationRepository(database).severities_by_event(
        ["e1", "e2", "e3"]
    )

    assert result == {"e1": [L.HIGH, L.LOW], "e2": [L.UNKNOWN], "e3": []}
    query = collection.find.call_args.args[0]
    assert query == {"event_id": {"$in": ["e1", "e2", "e3"]}}


@pytest.mark.asyncio
async def test_repository_skips_query_for_no_events():
    collection = MagicMock()
    database = MagicMock()
    database.__getitem__.return_value = collection

    assert await AffectedLocationRepository(database).severities_by_event([]) == {}
    collection.find.assert_not_called()


@pytest.mark.asyncio
async def test_service_derives_severity_per_event():
    locations = AsyncMock()
    locations.severities_by_event.return_value = {"e1": [L.MODERATE], "e2": []}
    service = FloodEventService(AsyncMock(), locations)

    result = await service.severity_for_events(["e1", "e2"])

    assert result["e1"].severity == L.MODERATE
    assert result["e2"].severity == L.UNKNOWN


def test_api_returns_derived_severity(client):
    event = FloodEvent(event_id="e1", title="Flood", location_name="Patna", state="Bihar")
    service = AsyncMock()
    service.get_event.return_value = event
    service.list_events.return_value = [event]
    service.severity_for_events.return_value = {"e1": derive_event_severity([L.HIGH, L.UNKNOWN])}
    app.dependency_overrides[get_flood_event_service] = lambda: service

    detail = client.get("/api/v1/flood-events/e1").json()
    listed = client.get("/api/v1/flood-events").json()

    for body in (detail, listed[0]):
        assert body["severity"] == "HIGH"
        assert body["severity_basis"] == {
            "rule": SEVERITY_RULE,
            "location_count": 2,
            "assessed_location_count": 1,
        }
        assert body["is_sample"] is False
