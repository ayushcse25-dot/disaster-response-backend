"""Plan versions: replanning, manual allocation and read-time replan advice.

Every replan or manual allocation creates a new plan document with version + 1
and marks the previous one as superseded. Callers must send the version they
last saw (expected_version); a mismatch is a conflict, never a silent overwrite.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError

from app.models.allocation_plan import AllocationPlanRecord, AllocationPlanView
from app.models.enums import EventStatus, EventVerificationStatus
from app.models.resource_inventory import ResourceInventory
from app.models.resource_need import ResourceNeed
from app.models.response_team import ResponseTeam
from app.services.allocation_engine import (
    _ELIGIBLE_NEED_STATUSES,
    _NEED_RESOURCE_TYPES,
    _NEED_TEAM_CAPABILITIES,
    AllocationDecision,
    _normalise_unit,
    inventory_ineligibility_reasons,
    team_ineligibility_reasons,
)
from app.services.allocation_plan_service import AllocationPlanService
from app.services.resource_freshness import ResourceFreshness, inventory_status_fields

PLANS = "allocation_plans"


class PlanLifecycleError(Exception):
    def __init__(self, code: str, detail: Any) -> None:
        super().__init__(str(detail))
        self.code = code
        self.detail = detail


class PlanNotFound(PlanLifecycleError):
    pass


class PlanVersionConflict(PlanLifecycleError):
    pass


class ManualAllocationInvalid(PlanLifecycleError):
    pass


class ManualAllocationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    need_id: str = Field(min_length=1, max_length=100)
    inventory_id: str = Field(min_length=1, max_length=100)
    team_id: str = Field(min_length=1, max_length=100)
    quantity: float = Field(gt=0)


def _record(document: dict[str, Any]) -> AllocationPlanRecord:
    document = dict(document)
    document["plan_id"] = document.pop("_id")
    return AllocationPlanRecord.model_validate(document)


class PlanLifecycleService:
    def __init__(self, database: Any, plan_service: AllocationPlanService) -> None:
        self.database = database
        self.plans = database[PLANS]
        self.plan_service = plan_service

    async def _load_current(self, plan_id: str, expected_version: int) -> dict[str, Any]:
        document = await self.plans.find_one({"_id": plan_id})
        if document is None:
            raise PlanNotFound("PLAN_NOT_FOUND", "Allocation plan not found.")
        if document.get("superseded_by_plan_id"):
            raise PlanVersionConflict(
                "PLAN_SUPERSEDED",
                f"Plan was superseded by {document['superseded_by_plan_id']}.",
            )
        current = int(document.get("version") or 1)
        if current != expected_version:
            raise PlanVersionConflict(
                "VERSION_CONFLICT",
                f"Plan is at version {current}, not {expected_version}.",
            )
        return document

    async def _store_successor(
        self, previous: dict[str, Any], record: AllocationPlanRecord
    ) -> AllocationPlanRecord:
        """Insert the new version, then claim the previous one as superseded."""
        document = record.model_dump(mode="json")
        document["_id"] = document.pop("plan_id")
        try:
            await self.plans.insert_one(document)
        except DuplicateKeyError as exc:
            raise PlanVersionConflict(
                "VERSION_CONFLICT", "Another request already created this version."
            ) from exc

        update: dict[str, Any] = {"superseded_by_plan_id": record.plan_id}
        if previous.get("approval_status", "PENDING") == "PENDING":
            update["approval_status"] = "SUPERSEDED"
        claimed = await self.plans.update_one(
            {"_id": previous["_id"], "superseded_by_plan_id": None}, {"$set": update}
        )
        if claimed.matched_count != 1:
            await self.plans.delete_one({"_id": record.plan_id})
            raise PlanVersionConflict(
                "VERSION_CONFLICT", "The plan was superseded by another request."
            )
        return record

    async def replan(
        self, plan_id: str, *, expected_version: int, actor_id: str
    ) -> AllocationPlanRecord:
        previous = await self._load_current(plan_id, expected_version)
        record, _ = await self.plan_service.build_for_event(
            previous["event_id"],
            organisation_id=previous.get("ngo_id"),
            version=expected_version + 1,
        )
        record.supersedes_plan_id = plan_id
        record.created_by = actor_id
        record.is_sample = bool(previous.get("is_sample"))
        return await self._store_successor(previous, record)

    async def manual_allocation(
        self,
        plan_id: str,
        *,
        expected_version: int,
        actor_id: str,
        reason: str,
        items: list[ManualAllocationItem],
    ) -> AllocationPlanRecord:
        if not reason.strip():
            raise ManualAllocationInvalid("REASON_REQUIRED", "A reason is required.")
        if not items:
            raise ManualAllocationInvalid("MANUAL_ALLOCATION_INVALID", "At least one item is required.")
        previous = await self._load_current(plan_id, expected_version)
        event_id = previous["event_id"]
        now = datetime.now(timezone.utc)

        manual_need_ids = {item.need_id for item in items}
        manual_team_ids = {item.team_id for item in items}
        kept = [
            d for d in previous.get("plan", {}).get("decisions", [])
            if d["need_id"] not in manual_need_ids and d["team_id"] not in manual_team_ids
        ]
        used_stock: dict[str, float] = {}
        for d in kept:
            used_stock[d["inventory_id"]] = used_stock.get(d["inventory_id"], 0) + d["proposed_quantity"]

        problems: list[dict[str, Any]] = []
        decisions: list[AllocationDecision] = []
        seen_teams: set[str] = set()
        for index, item in enumerate(items):
            reasons: list[str] = []
            need_doc = await self.database["resource_needs"].find_one({"_id": item.need_id})
            stock_doc = await self.database["resource_inventory"].find_one({"_id": item.inventory_id})
            team_doc = await self.database["response_teams"].find_one({"_id": item.team_id})

            need = stock = team = None
            if need_doc is None:
                reasons.append(f"Need '{item.need_id}' does not exist.")
            else:
                need_doc["need_id"] = need_doc.pop("_id")
                need = ResourceNeed.model_validate(need_doc)
                if need.event_id != event_id:
                    reasons.append("Need belongs to a different event.")
                if need.status not in _ELIGIBLE_NEED_STATUSES:
                    reasons.append(f"Need status {need.status} is not eligible for allocation.")
            if stock_doc is None:
                reasons.append(f"Inventory '{item.inventory_id}' does not exist.")
            else:
                stock_doc["inventory_id"] = stock_doc.pop("_id")
                stock = ResourceInventory.model_validate(stock_doc)
                reasons += [f"Inventory: {r}" for r in inventory_ineligibility_reasons(stock, now)]
            if team_doc is None:
                reasons.append(f"Team '{item.team_id}' does not exist.")
            else:
                team_doc["team_id"] = team_doc.pop("_id")
                team = ResponseTeam.model_validate(team_doc)
                reasons += [f"Team: {r}" for r in team_ineligibility_reasons(team, now)]
            if item.team_id in seen_teams:
                reasons.append("Team appears more than once.")
            seen_teams.add(item.team_id)

            if need and stock:
                if stock.resource_type not in _NEED_RESOURCE_TYPES[need.need_type]:
                    reasons.append(
                        f"Resource type {stock.resource_type} is not compatible with need type {need.need_type}."
                    )
                if not need.quantity_unit or _normalise_unit(stock.quantity_unit) != _normalise_unit(need.quantity_unit):
                    reasons.append("Inventory unit does not match the need unit.")
                available = (
                    stock.quantity_total - stock.quantity_reserved - stock.quantity_deployed
                    - used_stock.get(stock.inventory_id, 0)
                )
                if item.quantity > available:
                    reasons.append(f"Quantity {item.quantity:g} exceeds unreserved stock {max(available, 0):g}.")
            if need and team and not set(team.capabilities) & _NEED_TEAM_CAPABILITIES[need.need_type]:
                reasons.append(f"Team has no capability compatible with need type {need.need_type}.")

            if reasons:
                problems.append({"index": index, "need_id": item.need_id, "reasons": reasons})
                continue
            assert need is not None and need.quantity_unit is not None
            used_stock[item.inventory_id] = used_stock.get(item.inventory_id, 0) + item.quantity
            decisions.append(AllocationDecision(
                decision_id=f"manual:{item.need_id}:{item.inventory_id}:{item.team_id}",
                need_id=item.need_id,
                location_id=need.location_id,
                inventory_id=item.inventory_id,
                team_id=item.team_id,
                proposed_quantity=item.quantity,
                quantity_unit=need.quantity_unit,
                rationale=[f"Manual allocation by {actor_id}: {reason.strip()}"],
                constraints=["Proposal only; human review and approval are required."],
            ))

        if problems:
            raise ManualAllocationInvalid("MANUAL_ALLOCATION_INVALID", problems)

        base = _record(previous)
        plan = base.plan.model_copy(update={
            "generated_at": now,
            "status": "READY",
            "blocked_reasons": [],
            "decisions": [AllocationDecision.model_validate(d) for d in kept] + decisions,
            "unallocated_needs": [u for u in base.plan.unallocated_needs if u.need_id not in manual_need_ids],
            "notes": base.plan.notes + [f"Manual allocation by {actor_id}."],
        })
        record = AllocationPlanRecord(
            plan_id=str(uuid4()),
            event_id=event_id,
            plan=plan,
            created_at=now,
            version=expected_version + 1,
            source="MANUAL",
            supersedes_plan_id=plan_id,
            created_by=actor_id,
            manual_reason=reason.strip(),
            ngo_id=base.ngo_id,
            is_sample=base.is_sample,
        )
        return await self._store_successor(previous, record)

    async def view(self, record: AllocationPlanRecord) -> AllocationPlanView:
        reasons = await replan_reasons(self.database, record)
        return AllocationPlanView(
            **record.model_dump(), replan_suggested=bool(reasons), replan_reasons=reasons
        )


async def replan_reasons(
    database: Any, record: AllocationPlanRecord, now: datetime | None = None
) -> list[str]:
    """Why this plan should be replanned, computed from current data at read time."""
    if record.superseded_by_plan_id or record.approval_status in ("REJECTED", "SUPERSEDED"):
        return []
    now = now or datetime.now(timezone.utc)
    reasons = list(record.replan_flags)

    event = await database["flood_events"].find_one({"_id": record.event_id})
    if event is None or event.get("status") != EventStatus.ACTIVE.value or (
        event.get("verification_status") != EventVerificationStatus.VERIFIED.value
    ):
        reasons.append("Flood event is no longer ACTIVE and VERIFIED.")

    pending = record.approval_status == "PENDING"
    for decision in record.plan.decisions:
        stock_doc = await database["resource_inventory"].find_one({"_id": decision.inventory_id})
        if stock_doc is None:
            reasons.append(f"Inventory {decision.inventory_id} no longer exists.")
        else:
            stock_doc["inventory_id"] = stock_doc.pop("_id")
            stock = ResourceInventory.model_validate(stock_doc)
            if pending:
                problems = inventory_ineligibility_reasons(stock, now)
                if problems:
                    reasons.append(f"Inventory {stock.inventory_id}: {' '.join(problems)}")
            elif inventory_status_fields(stock, now).freshness in (
                ResourceFreshness.STALE, ResourceFreshness.UNVERIFIED
            ):
                reasons.append(f"Inventory {stock.inventory_id} check-in is stale.")
        if pending:
            team_doc = await database["response_teams"].find_one({"_id": decision.team_id})
            if team_doc is None:
                reasons.append(f"Team {decision.team_id} no longer exists.")
            else:
                team_doc["team_id"] = team_doc.pop("_id")
                problems = team_ineligibility_reasons(ResponseTeam.model_validate(team_doc), now)
                if problems:
                    reasons.append(f"Team {decision.team_id}: {' '.join(problems)}")
    return reasons
