"""Transactional approval and rejection of allocation proposals.

Approval reserves resources and assigns teams. It never dispatches teams.
MongoDB transactions require a replica set or sharded deployment.
"""
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any
from uuid import uuid4

from pymongo.errors import PyMongoError

from app.models.decision_audit import DecisionAction, DecisionAudit
from app.models.deployment_assignment import AssignmentStatus, DeploymentAssignment
from app.models.enums import EventStatus, EventVerificationStatus
from app.models.resource_inventory import InventoryStatus
from app.models.response_team import TeamStatus


class ApprovalError(Exception):
    """Base class for expected approval-workflow failures."""


class ApprovalNotFound(ApprovalError):
    pass


class ApprovalConflict(ApprovalError):
    pass


class ApprovalValidationError(ApprovalError):
    pass


class ApprovalServiceUnavailable(ApprovalError):
    pass


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _fresh(value: Any, maximum_age: timedelta, now: datetime) -> bool:
    parsed = _parse_timestamp(value)
    return parsed is not None and timedelta(0) <= now - parsed <= maximum_age


def _normalise_unit(value: str) -> str:
    return " ".join(value.strip().casefold().split())


class AllocationApprovalService:
    """Apply a human decision and all associated writes atomically."""

    def __init__(self, database: Any) -> None:
        self.database = database

    async def approve(
        self, plan_id: str, *, actor_id: str, actor_type: str, reason: str
    ) -> dict[str, Any]:
        if not actor_id.strip() or not actor_type.strip() or not reason.strip():
            raise ApprovalValidationError("Actor ID, actor type, and approval reason are required.")
        if len(actor_id) > 100 or len(actor_type) > 50 or len(reason) > 3000:
            raise ApprovalValidationError("Approval request exceeds field limits.")

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        client = self.database.client
        try:
            async with client.start_session() as session:
                async with await session.start_transaction():
                    plans = self.database["allocation_plans"]
                    events = self.database["flood_events"]
                    inventory_collection = self.database["resource_inventory"]
                    teams_collection = self.database["response_teams"]
                    assignments_collection = self.database["deployment_assignments"]
                    audits_collection = self.database["decision_audits"]

                    plan_doc = await plans.find_one({"_id": plan_id}, session=session)
                    if plan_doc is None:
                        raise ApprovalNotFound("Allocation plan not found.")
                    if plan_doc.get("approval_status", "PENDING") != "PENDING":
                        raise ApprovalConflict("This allocation plan has already been decided.")

                    plan = plan_doc.get("plan", {})
                    if plan.get("status") != "READY":
                        raise ApprovalValidationError("Only READY allocation proposals can be approved.")
                    decisions = plan.get("decisions", [])
                    if not decisions:
                        raise ApprovalValidationError("Cannot approve an allocation plan with no decisions.")

                    event_id = plan_doc.get("event_id")
                    event = await events.find_one({"_id": event_id}, session=session)
                    if event is None:
                        raise ApprovalConflict("The flood event no longer exists.")
                    if (
                        event.get("status") != EventStatus.ACTIVE.value
                        or event.get("verification_status") != EventVerificationStatus.VERIFIED.value
                    ):
                        raise ApprovalConflict("The flood event must remain ACTIVE and VERIFIED.")

                    claimed = await plans.update_one(
                        {
                            "_id": plan_id,
                            "$or": [
                                {"approval_status": "PENDING"},
                                {"approval_status": {"$exists": False}},
                            ],
                        },
                        {"$set": {
                            "approval_status": "APPROVED",
                            "approved_by": actor_id,
                            "approved_at": now_iso,
                        }},
                        session=session,
                    )
                    if claimed.matched_count != 1:
                        raise ApprovalConflict("The plan was already decided by another request.")

                    seen_teams: set[str] = set()
                    for decision in decisions:
                        if decision.get("status") != "PROPOSED":
                            raise ApprovalValidationError("The plan contains a non-proposed decision.")

                        quantity = decision.get("proposed_quantity")
                        unit = decision.get("quantity_unit")
                        inventory_id = decision.get("inventory_id")
                        team_id = decision.get("team_id")
                        location_id = decision.get("location_id")
                        need_id = decision.get("need_id")
                        if (
                            not isinstance(quantity, (int, float))
                            or isinstance(quantity, bool)
                            or not isfinite(quantity)
                            or quantity <= 0
                            or not all(isinstance(v, str) and v.strip() for v in (
                                unit, inventory_id, team_id, location_id, need_id
                            ))
                        ):
                            raise ApprovalValidationError("A proposal decision contains invalid fields.")
                        if team_id in seen_teams:
                            raise ApprovalValidationError("A response team appears more than once in the plan.")
                        seen_teams.add(team_id)

                        stock = await inventory_collection.find_one({"_id": inventory_id}, session=session)
                        if stock is None:
                            raise ApprovalConflict(f"Inventory '{inventory_id}' no longer exists.")
                        if (
                            stock.get("status") != InventoryStatus.AVAILABLE.value
                            or stock.get("availability_confirmed") is not True
                            or not _fresh(stock.get("last_verified_at"), timedelta(hours=24), now)
                            or _normalise_unit(str(stock.get("quantity_unit", ""))) != _normalise_unit(unit)
                        ):
                            raise ApprovalConflict(
                                f"Inventory '{inventory_id}' is unavailable, stale, unconfirmed, or has an incompatible unit."
                            )

                        team = await teams_collection.find_one({"_id": team_id}, session=session)
                        if team is None:
                            raise ApprovalConflict(f"Response team '{team_id}' no longer exists.")
                        if (
                            team.get("status") != TeamStatus.AVAILABLE.value
                            or team.get("availability_confirmed") is not True
                            or team.get("current_assignment_id") is not None
                            or not isinstance(team.get("personnel_count"), int)
                            or isinstance(team.get("personnel_count"), bool)
                            or team.get("personnel_count", 0) <= 0
                            or not _fresh(team.get("last_status_update"), timedelta(hours=2), now)
                        ):
                            raise ApprovalConflict(f"Response team '{team_id}' is unavailable or stale.")

                        stock_update = await inventory_collection.update_one(
                            {
                                "_id": inventory_id,
                                "status": InventoryStatus.AVAILABLE.value,
                                "availability_confirmed": True,
                                "last_verified_at": stock.get("last_verified_at"),
                                "$expr": {
                                    "$gte": [
                                        {"$subtract": [
                                            {"$subtract": [
                                                {"$ifNull": ["$quantity_total", 0]},
                                                {"$ifNull": ["$quantity_reserved", 0]},
                                            ]},
                                            {"$ifNull": ["$quantity_deployed", 0]},
                                        ]},
                                        quantity,
                                    ]
                                },
                            },
                            {"$inc": {"quantity_reserved": quantity}, "$set": {"updated_at": now_iso}},
                            session=session,
                        )
                        if stock_update.matched_count != 1:
                            raise ApprovalConflict(
                                f"Inventory '{inventory_id}' no longer has sufficient unreserved stock."
                            )

                        assignment_id = str(uuid4())
                        assignment = DeploymentAssignment(
                            assignment_id=assignment_id,
                            event_id=event_id,
                            location_id=location_id,
                            team_id=team_id,
                            task_description=(
                                f"Fulfil resource need {need_id}: reserve {quantity:g} {unit}. "
                                "This is an approved assignment, not a dispatch instruction."
                            ),
                            status=AssignmentStatus.APPROVED,
                            recommendation_id=plan_id,
                            approved_by=actor_id,
                            approved_at=now,
                            created_at=now,
                            updated_at=now,
                        )
                        team_update = await teams_collection.update_one(
                            {
                                "_id": team_id,
                                "status": TeamStatus.AVAILABLE.value,
                                "availability_confirmed": True,
                                "current_assignment_id": None,
                                "personnel_count": {"$gt": 0},
                                "last_status_update": team.get("last_status_update"),
                            },
                            {"$set": {
                                "status": TeamStatus.ASSIGNED.value,
                                "current_assignment_id": assignment_id,
                                "updated_at": now_iso,
                            }},
                            session=session,
                        )
                        if team_update.matched_count != 1:
                            raise ApprovalConflict(f"Response team '{team_id}' changed during approval.")

                        assignment_doc = assignment.model_dump(mode="json")
                        assignment_doc["_id"] = assignment_doc.pop("assignment_id")
                        await assignments_collection.insert_one(assignment_doc, session=session)

                        audit = DecisionAudit(
                            audit_id=str(uuid4()),
                            event_id=event_id,
                            action=DecisionAction.ASSIGNMENT_CREATED,
                            recommendation_id=plan_id,
                            assignment_id=assignment_id,
                            actor_id=actor_id,
                            actor_type=actor_type,
                            reason=f"Assignment created while approving allocation plan {plan_id}. Approval reason: {reason.strip()}",
                            created_at=now,
                        )
                        audit_doc = audit.model_dump(mode="json")
                        audit_doc["_id"] = audit_doc.pop("audit_id")
                        await audits_collection.insert_one(audit_doc, session=session)

                    approval_audit = DecisionAudit(
                        audit_id=str(uuid4()),
                        event_id=event_id,
                        action=DecisionAction.RECOMMENDATION_APPROVED,
                        recommendation_id=plan_id,
                        actor_id=actor_id,
                        actor_type=actor_type,
                        reason=reason.strip(),
                        created_at=now,
                    )
                    audit_doc = approval_audit.model_dump(mode="json")
                    audit_doc["_id"] = audit_doc.pop("audit_id")
                    await audits_collection.insert_one(audit_doc, session=session)

                    result = dict(plan_doc)
                    result.pop("_id", None)
                    result["plan_id"] = plan_id
                    result["approval_status"] = "APPROVED"
                    result["approved_by"] = actor_id
                    result["approved_at"] = now
                    result["rejected_by"] = None
                    result["rejected_at"] = None
                    result["rejection_reason"] = None
                    return result
        except ApprovalError:
            raise
        except PyMongoError as exc:
            raise ApprovalServiceUnavailable("The approval transaction could not be completed.") from exc

    async def reject(
        self, plan_id: str, *, actor_id: str, actor_type: str, reason: str
    ) -> dict[str, Any]:
        if not actor_id.strip() or not actor_type.strip() or not reason.strip():
            raise ApprovalValidationError("Actor ID, actor type, and rejection reason are required.")
        if len(actor_id) > 100 or len(actor_type) > 50 or len(reason) > 3000:
            raise ApprovalValidationError("Rejection request exceeds field limits.")

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        try:
            async with self.database.client.start_session() as session:
                async with await session.start_transaction():
                    plans = self.database["allocation_plans"]
                    audits = self.database["decision_audits"]
                    plan_doc = await plans.find_one({"_id": plan_id}, session=session)
                    if plan_doc is None:
                        raise ApprovalNotFound("Allocation plan not found.")
                    if plan_doc.get("approval_status", "PENDING") != "PENDING":
                        raise ApprovalConflict("This allocation plan has already been decided.")

                    changed = await plans.update_one(
                        {
                            "_id": plan_id,
                            "$or": [
                                {"approval_status": "PENDING"},
                                {"approval_status": {"$exists": False}},
                            ],
                        },
                        {"$set": {
                            "approval_status": "REJECTED",
                            "rejected_by": actor_id,
                            "rejected_at": now_iso,
                            "rejection_reason": reason.strip(),
                        }},
                        session=session,
                    )
                    if changed.matched_count != 1:
                        raise ApprovalConflict("The plan was already decided by another request.")

                    audit = DecisionAudit(
                        audit_id=str(uuid4()),
                        event_id=plan_doc["event_id"],
                        action=DecisionAction.RECOMMENDATION_REJECTED,
                        recommendation_id=plan_id,
                        actor_id=actor_id,
                        actor_type=actor_type,
                        reason=reason.strip(),
                        created_at=now,
                    )
                    audit_doc = audit.model_dump(mode="json")
                    audit_doc["_id"] = audit_doc.pop("audit_id")
                    await audits.insert_one(audit_doc, session=session)

                    result = dict(plan_doc)
                    result.pop("_id", None)
                    result["plan_id"] = plan_id
                    result["approval_status"] = "REJECTED"
                    result["rejected_by"] = actor_id
                    result["rejected_at"] = now
                    result["rejection_reason"] = reason.strip()
                    result["approved_by"] = None
                    result["approved_at"] = None
                    return result
        except ApprovalError:
            raise
        except PyMongoError as exc:
            raise ApprovalServiceUnavailable("The rejection transaction could not be completed.") from exc
