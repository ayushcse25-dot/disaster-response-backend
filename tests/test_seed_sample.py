"""Tests for the sample seed script, using an in-memory database."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.models.affected_location import AffectedLocation
from app.models.allocation_plan import AllocationPlanRecord
from app.models.organisation import Organisation
from app.models.flood_event import FloodEvent
from app.models.flood_observation import FloodObservation
from app.models.resource_inventory import ResourceInventory
from app.models.resource_need import ResourceNeed
from app.models.response_team import ResponseTeam
from app.models.source import SourceRegistryEntry
from app.services.event_severity import derive_event_severity
from app.services.resource_freshness import inventory_status_fields, team_status_fields
from scripts import seed_sample
from scripts.seed_sample import SeedConflictError, build_sample_documents, seed

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


class FakeCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        for key, condition in query.items():
            value = doc.get(key)
            if isinstance(condition, dict):
                if "$in" in condition and value not in condition["$in"]:
                    return False
                if "$ne" in condition and value == condition["$ne"]:
                    return False
            elif value != condition:
                return False
        return True

    async def find_one(self, query: dict, projection=None):
        return next((d for d in self.docs.values() if self._matches(d, query)), None)

    async def replace_one(self, query: dict, document: dict, upsert: bool = False):
        existing = self.docs.get(document["_id"])
        if existing is not None and not self._matches(existing, query):
            raise RuntimeError("duplicate key")
        self.docs[document["_id"]] = dict(document)


class FakeDatabase(dict):
    def __missing__(self, name: str) -> FakeCollection:
        self[name] = FakeCollection()
        return self[name]


def test_sample_documents_are_valid_labelled_and_prefixed():
    documents = build_sample_documents(NOW)
    models = {
        "organisations": (Organisation, "organisation_id"),
        "sources": (SourceRegistryEntry, "source_id"),
        "flood_events": (FloodEvent, "event_id"),
        "affected_locations": (AffectedLocation, "location_id"),
        "flood_observations": (FloodObservation, "observation_id"),
        "resource_inventory": (ResourceInventory, "inventory_id"),
        "response_teams": (ResponseTeam, "team_id"),
        "resource_needs": (ResourceNeed, "need_id"),
        "allocation_plans": (AllocationPlanRecord, "plan_id"),
    }

    assert set(documents) == set(models)

    for collection_name, items in documents.items():
        model, id_field = models[collection_name]
        assert items
        for item in items:
            assert item["_id"].startswith("sample-")
            assert item["is_sample"] is True
            data = {k: v for k, v in item.items() if k != "_id"}
            model.model_validate({**data, id_field: item["_id"]})


def test_sample_references_are_consistent():
    documents = build_sample_documents(NOW)
    event_ids = {d["_id"] for d in documents["flood_events"]}
    source_ids = {d["_id"] for d in documents["sources"]}

    assert {d["event_id"] for d in documents["affected_locations"]} <= event_ids
    assert {d["event_id"] for d in documents["flood_observations"]} <= event_ids
    assert {d["source_id"] for d in documents["flood_observations"]} <= source_ids
    location_ids = {d["_id"] for d in documents["affected_locations"]}
    assert {d["location_id"] for d in documents["resource_needs"]} <= location_ids
    assert {d["event_id"] for d in documents["resource_needs"]} <= event_ids
    assert {d["event_id"] for d in documents["allocation_plans"]} <= event_ids


def _load(model, item, id_field):
    data = {k: v for k, v in item.items() if k != "_id"}
    return model.model_validate({**data, id_field: item["_id"]})


def test_sample_resources_cover_each_freshness_value():
    documents = build_sample_documents(NOW)

    inventory = [_load(ResourceInventory, d, "inventory_id") for d in documents["resource_inventory"]]
    teams = [_load(ResponseTeam, d, "team_id") for d in documents["response_teams"]]

    assert [inventory_status_fields(i, NOW).freshness for i in inventory] == [
        "FRESH", "DUE", "STALE", "UNVERIFIED"
    ]
    assert [team_status_fields(t, NOW).freshness for t in teams] == ["FRESH", "DUE", "STALE"]


def test_sample_plans_come_from_the_engine():
    plans = {
        d["_id"]: _load(AllocationPlanRecord, d, "plan_id")
        for d in build_sample_documents(NOW)["allocation_plans"]
    }

    ready = plans["sample-plan-001"]
    assert ready.plan.status == "READY"
    assert ready.approval_status == "PENDING"
    assert {(d.need_id, d.inventory_id, d.team_id) for d in ready.plan.decisions} == {
        ("sample-need-001", "sample-inv-001", "sample-team-001"),
        ("sample-need-002", "sample-inv-002", "sample-team-002"),
    }
    assert {u.need_id for u in ready.plan.unallocated_needs} == {
        "sample-need-003", "sample-need-004"
    }
    assert plans["sample-plan-002"].plan.status == "BLOCKED"


def test_sample_events_cover_each_severity_outcome():
    documents = build_sample_documents(NOW)

    def severity(event_id):
        return derive_event_severity(
            d["severity"] for d in documents["affected_locations"] if d["event_id"] == event_id
        ).severity

    assert severity("sample-event-001") == "CRITICAL"
    assert severity("sample-event-002") == "MODERATE"
    assert severity("sample-event-003") == "UNKNOWN"


@pytest.mark.asyncio
async def test_seed_is_idempotent():
    database = FakeDatabase()

    first = await seed(database, NOW)
    second = await seed(database, NOW)

    assert first == second
    assert len(database["flood_events"].docs) == first["flood_events"] == 3
    assert len(database["flood_observations"].docs) == 5
    assert len(database["allocation_plans"].docs) == first["allocation_plans"] == 2


@pytest.mark.asyncio
async def test_seed_leaves_non_sample_records_alone():
    database = FakeDatabase()
    real = {"_id": "real-event", "title": "Real", "is_sample": False}
    database["flood_events"].docs["real-event"] = dict(real)

    await seed(database, NOW)

    assert database["flood_events"].docs["real-event"] == real


@pytest.mark.asyncio
async def test_seed_aborts_before_writing_when_sample_id_is_taken():
    database = FakeDatabase()
    database["flood_observations"].docs["sample-obs-001"] = {"_id": "sample-obs-001"}

    with pytest.raises(SeedConflictError, match="sample-obs-001"):
        await seed(database, NOW)

    assert database["flood_events"].docs == {}
    assert database["sources"].docs == {}
    assert database["flood_observations"].docs == {"sample-obs-001": {"_id": "sample-obs-001"}}


def test_main_refuses_without_confirm(capsys):
    with patch.object(seed_sample, "_run") as run:
        assert seed_sample.main([]) == 2

    run.assert_not_called()
    assert "--confirm" in capsys.readouterr().err
