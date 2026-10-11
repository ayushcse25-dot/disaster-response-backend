from datetime import datetime, timezone
from copy import deepcopy

import pytest

from app.models.field_report import FieldReportType
from app.services.live_response_service import (
    LiveResponseConflict,
    LiveResponseNotFound,
    LiveResponseService,
)




class FakeTransaction:
    def __init__(self, database):
        self.database = database
        self.snapshot = None

    async def __aenter__(self):
        self.snapshot = {
            name: deepcopy(collection.documents)
            for name, collection in self.database.collections.items()
        }
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        if exc_type is not None:
            for name, documents in self.snapshot.items():
                self.database.collections[name].documents = documents
        return False


class FakeSession:
    def __init__(self, database):
        self.database = database

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def start_transaction(self):
        return FakeTransaction(self.database)


class FakeClient:
    def __init__(self, database):
        self.database = database

    def start_session(self):
        return FakeSession(self.database)

class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, *args, **kwargs):
        return self

    def skip(self, count):
        self.documents = self.documents[count:]
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    async def to_list(self, length=None):
        return self.documents[:length] if length is not None else self.documents


class FakeCollection:
    def __init__(self, documents=None, fail_on=None):
        self.documents = {
            document["_id"]: dict(document)
            for document in (documents or [])
        }
        self.fail_on = fail_on

    async def find_one(self, query, session=None):
        if self.fail_on == "find_one":
            raise RuntimeError("Simulated database read failure")

        for document in self.documents.values():
            if all(document.get(k) == v for k, v in query.items()):
                return dict(document)
        return None

    def find(self, query, session=None):
        matches = [
            dict(document)
            for document in self.documents.values()
            if all(document.get(k) == v for k, v in query.items())
        ]
        return FakeCursor(matches)

    async def insert_one(self, document, session=None):
        if self.fail_on == "insert_one":
            raise RuntimeError("Simulated database write failure")

        stored = dict(document)
        document_id = stored.get("_id")

        if document_id is None:
            document_id = (
                stored.get("report_id")
                or stored.get("recommendation_id")
                or stored.get("audit_id")
                or f"generated-{len(self.documents) + 1}"
            )
            stored["_id"] = document_id

        self.documents[document_id] = stored

        class Result:
            inserted_id = document_id

        return Result()

    async def update_many(self, query, update, session=None):
        if self.fail_on == "update_many":
            raise RuntimeError("Simulated database update failure")

        matched = 0
        for document_id, document in list(self.documents.items()):
            if all(document.get(k) == v for k, v in query.items()):
                updated = dict(document)
                updated.update(update.get("$set", {}))
                self.documents[document_id] = updated
                matched += 1

        class Result:
            matched_count = matched
            modified_count = matched

        return Result()


class FakeDatabase:
    def __init__(
        self,
        *,
        missing_event=False,
        missing_team=False,
        fail_collection=None,
        fail_operation=None,
    ):
        self.collections = {
            "flood_events": FakeCollection(
                [] if missing_event else [
                    {"_id": "flood-001", "name": "Test flood"}
                ]
            ),
            "response_teams": FakeCollection(
                [] if missing_team else [
                    {"_id": "team-001", "name": "Rescue team"}
                ]
            ),
            "field_reports": FakeCollection(
                fail_on=fail_operation
                if fail_collection == "field_reports" else None
            ),
            "affected_locations": FakeCollection([
                {
                    "_id": "location-001",
                    "event_id": "flood-001",
                    "reassessment_required": False,
                }
            ]),
            "resource_needs": FakeCollection([
                {
                    "_id": "need-001",
                    "event_id": "flood-001",
                    "reassessment_required": False,
                }
            ]),
            "reallocation_recommendations": FakeCollection(
                fail_on=fail_operation
                if fail_collection == "reallocation_recommendations"
                else None
            ),
            "decision_audits": FakeCollection(
                fail_on=fail_operation
                if fail_collection == "decision_audits" else None
            ),
        }
        self.client = FakeClient(self)

    def __getitem__(self, name):
        return self.collections[name]


def valid_payload(**overrides):
    payload = {
        "team_id": "team-001",
        "report_type": FieldReportType.ROAD_BLOCKED,
        "title": "Bridge access blocked",
        "description": "The main bridge is blocked by flood debris.",
        "location_name": "North bridge",
        "observed_at": datetime.now(timezone.utc),
    }
    payload.update(overrides)
    return payload


async def call_service(db, **overrides):
    return await LiveResponseService(db).submit_report(
        event_id="flood-001",
        **valid_payload(**overrides),
    )


@pytest.mark.asyncio
async def test_valid_report_creates_recommendation_and_audits():
    db = FakeDatabase()

    result = await call_service(db)

    assert result["reassessment_requested"] is True
    assert result["dispatch_performed"] is False
    assert result["allocation_recalculated"] is False
    assert len(db["field_reports"].documents) == 1
    assert len(db["reallocation_recommendations"].documents) == 1
    assert len(db["decision_audits"].documents) == 2

    report = result["report"]
    recommendation = result["recommendation"]

    assert report["event_id"] == "flood-001"
    assert report["team_id"] == "team-001"
    assert recommendation["status"] == "PROPOSED"
    assert recommendation["supporting_report_ids"] == [report["report_id"]]
    assert "location-001" in recommendation["affected_location_ids"]
    assert "need-001" in recommendation["affected_need_ids"]

    assert db["affected_locations"].documents["location-001"][
        "reassessment_required"
    ] is True
    assert db["resource_needs"].documents["need-001"][
        "reassessment_required"
    ] is True


@pytest.mark.asyncio
async def test_missing_event_is_rejected_before_writes():
    db = FakeDatabase(missing_event=True)

    with pytest.raises(LiveResponseNotFound):
        await call_service(db)

    assert not db["field_reports"].documents
    assert not db["reallocation_recommendations"].documents


@pytest.mark.asyncio
async def test_missing_team_is_rejected_before_writes():
    db = FakeDatabase(missing_team=True)

    with pytest.raises(LiveResponseNotFound):
        await call_service(db)

    assert not db["field_reports"].documents
    assert not db["reallocation_recommendations"].documents


@pytest.mark.asyncio
async def test_assignment_linked_report_is_rejected():
    db = FakeDatabase()

    with pytest.raises(LiveResponseConflict):
        await call_service(db, assignment_id="assignment-001")

    assert not db["field_reports"].documents


@pytest.mark.asyncio
async def test_resource_shortage_generates_resource_reallocation():
    db = FakeDatabase()

    result = await call_service(
        db,
        report_type=FieldReportType.RESOURCE_SHORTAGE,
        title="Rescue supplies depleted",
        description="The team has run out of drinking water.",
    )

    assert result["recommendation"]["recommendation_type"] == (
        "RESOURCE_REALLOCATION"
    )


@pytest.mark.asyncio
async def test_medical_emergency_generates_additional_support():
    db = FakeDatabase()

    result = await call_service(
        db,
        report_type=FieldReportType.MEDICAL_EMERGENCY,
        title="Urgent medical assistance needed",
        description="An injured resident needs medical assistance.",
    )

    assert result["recommendation"]["recommendation_type"] == (
        "ADDITIONAL_SUPPORT"
    )


@pytest.mark.asyncio
async def test_database_read_failure_does_not_create_report():
    db = FakeDatabase()
    db["flood_events"].fail_on = "find_one"

    with pytest.raises(RuntimeError, match="database read failure"):
        await call_service(db)

    assert not db["field_reports"].documents


@pytest.mark.asyncio
async def test_audit_write_failure_rolls_back_report_and_recommendation():
    db = FakeDatabase(
        fail_collection="decision_audits",
        fail_operation="insert_one",
    )

    with pytest.raises(RuntimeError, match="database write failure"):
        await call_service(db)

    assert not db["field_reports"].documents
    assert not db["reallocation_recommendations"].documents
    assert not db["decision_audits"].documents
    assert db["affected_locations"].documents["location-001"][
        "reassessment_required"
    ] is False
    assert db["resource_needs"].documents["need-001"][
        "reassessment_required"
    ] is False
