"""Tests for the read-only flood observation endpoint."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.flood_observations import get_flood_observation_service
from app.main import app
from app.models.enums import ObservationType, SourceCategory
from app.models.flood_event import FloodEvent
from app.models.flood_observation import FloodObservation
from app.models.source import SourceRegistryEntry
from app.repositories.flood_observation_repository import FloodObservationRepository
from app.repositories.source_repository import SourceRepository
from app.schemas.flood_observation import FRESHNESS_RULE, Freshness
from app.services.flood_observation_service import (
    FloodObservationService,
    classify_freshness,
)

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def make_observation(observation_id="obs-1", source_id="src-1", hours_ago=2.0):
    return FloodObservation(
        observation_id=observation_id,
        event_id="e1",
        source_id=source_id,
        observation_type=ObservationType.RIVER_LEVEL,
        title="River above danger mark",
        description="Gauge reading above danger level.",
        location_name="Patna",
        state="Bihar",
        observed_at=NOW - timedelta(hours=hours_ago),
        received_at=NOW - timedelta(hours=hours_ago) + timedelta(minutes=5),
        evidence_reference="s3://private/raw.json",
    )


SOURCE = SourceRegistryEntry(
    source_id="src-1",
    name="Central Water Commission",
    category=SourceCategory.RIVER_MONITORING,
    access_method="API",
)


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(minutes=59), Freshness.FRESH),
        (timedelta(hours=1), Freshness.RECENT),
        (timedelta(hours=23, minutes=59), Freshness.RECENT),
        (timedelta(hours=24), Freshness.STALE),
    ],
)
def test_classify_freshness(age, expected):
    assert classify_freshness(NOW - age, NOW) == expected


def make_service(event=True, observations=(), sources=None):
    events = AsyncMock()
    events.get_by_id.return_value = (
        FloodEvent(event_id="e1", title="Flood", location_name="Patna", state="Bihar")
        if event
        else None
    )
    obs_repo = AsyncMock()
    obs_repo.list_by_event.return_value = list(observations)
    source_repo = AsyncMock()
    source_repo.get_many.return_value = sources or {}
    return FloodObservationService(events, obs_repo, source_repo), obs_repo, source_repo


@pytest.mark.asyncio
async def test_service_joins_source_name_and_hides_evidence_reference():
    service, _, source_repo = make_service(
        observations=[make_observation(), make_observation("obs-2", "src-missing", 30)],
        sources={"src-1": SOURCE},
    )

    result = await service.list_for_event("e1", now=NOW)

    first, second = result
    assert first.source_name == "Central Water Commission"
    assert first.source_category == SourceCategory.RIVER_MONITORING
    assert first.freshness == Freshness.RECENT
    assert first.freshness_rule == FRESHNESS_RULE
    assert first.received_at > first.observed_at
    assert second.source_name is None
    assert second.freshness == Freshness.STALE
    assert "evidence_reference" not in first.model_dump()
    source_repo.get_many.assert_awaited_once_with(["src-1", "src-missing"])


@pytest.mark.asyncio
async def test_service_returns_none_for_missing_event():
    service, obs_repo, _ = make_service(event=False)

    assert await service.list_for_event("nope") is None
    obs_repo.list_by_event.assert_not_awaited()


def test_api_lists_observations(client):
    service = AsyncMock()
    service.list_for_event.return_value = []
    app.dependency_overrides[get_flood_observation_service] = lambda: service

    response = client.get("/api/v1/flood-events/e1/observations?limit=10&skip=5")

    assert response.status_code == 200
    assert response.json() == []
    service.list_for_event.assert_awaited_once_with("e1", limit=10, skip=5)


def test_api_returns_404_for_missing_event(client):
    service = AsyncMock()
    service.list_for_event.return_value = None
    app.dependency_overrides[get_flood_observation_service] = lambda: service

    response = client.get("/api/v1/flood-events/nope/observations")

    assert response.status_code == 404
    assert response.json() == {"detail": "Flood event not found."}


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "skip=-1"])
def test_api_rejects_invalid_pagination(client, query):
    app.dependency_overrides[get_flood_observation_service] = lambda: AsyncMock()

    assert client.get(f"/api/v1/flood-events/e1/observations?{query}").status_code == 422


def mock_collection(documents):
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=documents)
    collection = MagicMock()
    collection.find.return_value = cursor
    database = MagicMock()
    database.__getitem__.return_value = collection
    return database, collection, cursor


@pytest.mark.asyncio
async def test_observation_repository_filters_by_event_newest_first():
    document = make_observation().model_dump(mode="json")
    document["_id"] = document.pop("observation_id")
    database, collection, cursor = mock_collection([document])

    result = await FloodObservationRepository(database).list_by_event("e1", limit=5, skip=1)

    assert [o.observation_id for o in result] == ["obs-1"]
    collection.find.assert_called_once_with({"event_id": "e1"})
    cursor.sort.assert_called_once_with("observed_at", -1)


@pytest.mark.asyncio
async def test_source_repository_returns_entries_by_id():
    document = SOURCE.model_dump(mode="json")
    document["_id"] = document.pop("source_id")
    database, collection, _ = mock_collection([document])

    result = await SourceRepository(database).get_many(["src-1", "src-1"])

    assert result["src-1"].name == "Central Water Commission"
    assert collection.find.call_args.args[0] == {"_id": {"$in": ["src-1"]}}


@pytest.mark.asyncio
async def test_source_repository_skips_query_for_no_ids():
    database, collection, _ = mock_collection([])

    assert await SourceRepository(database).get_many([]) == {}
    collection.find.assert_not_called()
