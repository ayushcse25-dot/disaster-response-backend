"""run_orchestration: verified event -> selected NGO -> READY plan on that NGO's resources.

Idempotent: the input digest covers every record that can change the outcome, so
running it again on unchanged data returns the stored result instead of a new plan.
Nothing is approved here; the plan waits for a human decision.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from pymongo.errors import DuplicateKeyError

from app.models.affected_location import AffectedLocation
from app.models.decision_audit import DecisionAction, DecisionAudit
from app.models.enums import EventStatus, EventVerificationStatus
from app.models.flood_event import FloodEvent
from app.models.organisation import Organisation
from app.models.resource_inventory import ResourceInventory
from app.models.resource_need import ResourceNeed
from app.models.response_team import ResponseTeam
from app.services.allocation_plan_service import AllocationPlanService
from app.services.orchestration.need_estimation import NeedEstimate, estimate_needs
from app.services.orchestration.ngo_selection import NgoSelection, select_ngo

ASSIGNMENTS = "ngo_assignments"
ORCHESTRATOR_ACTOR = "system:orchestrator"


class OrchestrationError(Exception):
    def __init__(self, code: str, detail: Any) -> None:
        super().__init__(str(detail))
        self.code = code
        self.detail = detail


class OrchestrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: str
    event_id: str
    ngo_id: str
    plan_id: str
    plan_version: int
    input_digest: str
    reused: bool
    selection: NgoSelection
    need_estimate: NeedEstimate
    created_at: datetime


async def _load(database: Any, collection: str, model: type[BaseModel], id_field: str,
                query: dict[str, Any] | None = None) -> list[Any]:
    documents = await database[collection].find(query or {}).to_list(length=5000)
    result = []
    for document in documents:
        document[id_field] = document.pop("_id")
        result.append(model.model_validate(document))
    return result


def _stored(document: dict[str, Any]) -> OrchestrationResult:
    fields = {k: v for k, v in document.items() if k in OrchestrationResult.model_fields}
    return OrchestrationResult.model_validate({**fields, "assignment_id": document["_id"], "reused": True})


def _digest(payload: dict[str, Any]) -> str:
    def dump(value: Any) -> Any:
        if isinstance(value, list):
            return sorted((dump(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value

    canonical = json.dumps({k: dump(v) for k, v in payload.items()}, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


async def run_orchestration(
    database: Any, plan_service: AllocationPlanService, event_id: str
) -> OrchestrationResult:
    document = await database["flood_events"].find_one({"_id": event_id})
    if document is None:
        raise OrchestrationError("EVENT_NOT_FOUND", f"Flood event '{event_id}' does not exist.")
    document["event_id"] = document.pop("_id")
    event = FloodEvent.model_validate(document)

    gate: list[str] = []
    if event.status != EventStatus.ACTIVE:
        gate.append(f"Event status is {event.status}, not ACTIVE.")
    if event.verification_status != EventVerificationStatus.VERIFIED:
        gate.append(f"Event verification is {event.verification_status}, not VERIFIED.")
    if event.location is None:
        gate.append("Event has no location.")
    if gate:
        raise OrchestrationError("ORCHESTRATION_BLOCKED", gate)
    assert event.location is not None

    organisations = await _load(database, "organisations", Organisation, "organisation_id")
    inventory = await _load(database, "resource_inventory", ResourceInventory, "inventory_id")
    teams = await _load(database, "response_teams", ResponseTeam, "team_id")
    locations = await _load(database, "affected_locations", AffectedLocation, "location_id",
                            {"event_id": event_id})
    needs = await _load(database, "resource_needs", ResourceNeed, "need_id", {"event_id": event_id})

    # Workload from other events only, so this event's own result does not change its digest.
    workload: dict[str, int] = {}
    cursor = await database[ASSIGNMENTS].aggregate([
        {"$match": {"status": "ACTIVE", "event_id": {"$ne": event_id}}},
        {"$group": {"_id": "$ngo_id", "n": {"$sum": 1}}},
    ])
    for row in await cursor.to_list():
        workload[row["_id"]] = row["n"]

    input_digest = _digest({
        "event": event, "organisations": organisations, "inventory": inventory,
        "teams": teams, "locations": locations, "needs": needs, "workload": workload,
    })
    existing = await database[ASSIGNMENTS].find_one({"event_id": event_id, "input_digest": input_digest})
    if existing is not None:
        return _stored(existing)

    estimate = estimate_needs(locations)
    need_types = {n.need_type for n in needs} or {n.need_type for n in estimate.needs}
    now = datetime.now(timezone.utc)
    selection = select_ngo(
        event_location=event.location, organisations=organisations, inventory=inventory,
        teams=teams, need_types=need_types, workload=workload, now=now,
    )
    if selection.selected is None:
        raise OrchestrationError(
            "NO_ELIGIBLE_NGO", {"explanation": selection.explanation, "excluded": selection.excluded}
        )
    ngo_id = selection.selected.organisation_id

    latest = await plan_service.plan_repository.latest_version(event_id)
    record, _ = await plan_service.build_for_event(
        event_id, organisation_id=ngo_id, version=latest + 1
    )
    record.created_by = ORCHESTRATOR_ACTOR
    record.is_sample = event.is_sample
    record.plan.notes.append(selection.explanation)
    await plan_service.plan_repository.create(record)

    assignment_id = str(uuid4())
    result = OrchestrationResult(
        assignment_id=assignment_id, event_id=event_id, ngo_id=ngo_id,
        plan_id=record.plan_id, plan_version=record.version, input_digest=input_digest,
        reused=False, selection=selection, need_estimate=estimate, created_at=now,
    )
    assignment = result.model_dump(mode="json", exclude={"assignment_id", "reused"})
    assignment.update({"_id": assignment_id, "status": "ACTIVE", "is_sample": event.is_sample})
    try:
        await database[ASSIGNMENTS].insert_one(assignment)
    except DuplicateKeyError:
        # A concurrent run with the same inputs won; drop our plan and return theirs.
        await database["allocation_plans"].delete_one({"_id": record.plan_id})
        return _stored(await database[ASSIGNMENTS].find_one(
            {"event_id": event_id, "input_digest": input_digest}
        ))
    await database[ASSIGNMENTS].update_many(
        {"event_id": event_id, "status": "ACTIVE", "_id": {"$ne": assignment_id}},
        {"$set": {"status": "SUPERSEDED"}},
    )

    audit = DecisionAudit(
        audit_id=str(uuid4()), event_id=event_id, action=DecisionAction.NGO_SELECTED,
        recommendation_id=record.plan_id, actor_id=ORCHESTRATOR_ACTOR, actor_type="SYSTEM",
        reason=selection.explanation, created_at=now,
    )
    audit_doc = audit.model_dump(mode="json")
    audit_doc["_id"] = audit_doc.pop("audit_id")
    await database["decision_audits"].insert_one(audit_doc)
    return result
