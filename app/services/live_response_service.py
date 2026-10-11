from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pymongo.errors import PyMongoError

from app.models.decision_audit import DecisionAction, DecisionAudit
from app.models.field_report import FieldReport, FieldReportStatus, FieldReportType
from app.models.reallocation_recommendation import (
    ReallocationRecommendation,
    RecommendationStatus,
    RecommendationType,
)


class LiveResponseError(Exception):
    """Base class for expected live-response workflow errors."""


class LiveResponseNotFound(LiveResponseError):
    """A referenced flood event or response team does not exist."""


class LiveResponseConflict(LiveResponseError):
    """The request conflicts with the currently supported workflow."""


class LiveResponseServiceUnavailable(LiveResponseError):
    """MongoDB could not complete the transactional workflow."""


class LiveResponseService:
    """
    Accept field reports and create reviewable operational recommendations.

    This service does not dispatch teams and does not claim to recalculate
    a complete allocation plan. MongoDB writes span multiple documents and
    are not atomic unless an appropriate transaction is explicitly used.
    """

    ALGORITHM_VERSION = "field-report-triage-1.0.0"

    def __init__(self, database: Any) -> None:
        self.database = database

    @staticmethod
    def _document(model: Any, identifier_field: str) -> dict[str, Any]:
        document = model.model_dump(mode="json")
        document["_id"] = document.pop(identifier_field)
        return document

    @staticmethod
    def _recommendation_type(report_type: FieldReportType) -> RecommendationType:
        mapping = {
            FieldReportType.ROAD_BLOCKED: RecommendationType.ROUTE_CHANGE,
            FieldReportType.ROAD_ACCESS_RESTORED: RecommendationType.ROUTE_CHANGE,
            FieldReportType.NEW_RESCUE_NEED: RecommendationType.ADDITIONAL_SUPPORT,
            FieldReportType.MEDICAL_EMERGENCY: RecommendationType.ADDITIONAL_SUPPORT,
            FieldReportType.RESOURCE_SHORTAGE: RecommendationType.RESOURCE_REALLOCATION,
            FieldReportType.TEAM_UNAVAILABLE: RecommendationType.REASSIGNMENT,
            FieldReportType.EQUIPMENT_FAILURE: RecommendationType.REASSIGNMENT,
        }
        return mapping.get(
            report_type,
            RecommendationType.ADDITIONAL_SUPPORT,
        )

    async def submit_report(
        self,
        event_id: str,
        *,
        team_id: str,
        report_type: FieldReportType,
        title: str,
        description: str,
        location_name: str,
        observed_at: datetime,
        coordinates: Any = None,
        assignment_id: str | None = None,
        evidence_reference: str | None = None,
    ) -> dict[str, Any]:
        """Persist a report and all associated effects atomically."""
        try:
            async with self.database.client.start_session() as session:
                async with await session.start_transaction():
                    return await self._submit_report_in_transaction(
                        event_id,
                        team_id=team_id,
                        report_type=report_type,
                        title=title,
                        description=description,
                        location_name=location_name,
                        observed_at=observed_at,
                        coordinates=coordinates,
                        assignment_id=assignment_id,
                        evidence_reference=evidence_reference,
                        session=session,
                    )
        except LiveResponseError:
            raise
        except PyMongoError as exc:
            raise LiveResponseServiceUnavailable(
                "The field report transaction could not be completed."
            ) from exc

    async def _submit_report_in_transaction(
        self,
        event_id: str,
        *,
        team_id: str,
        report_type: FieldReportType,
        title: str,
        description: str,
        location_name: str,
        observed_at: datetime,
        coordinates: Any = None,
        assignment_id: str | None = None,
        evidence_reference: str | None = None,
        session: Any,
    ) -> dict[str, Any]:
        if assignment_id is not None:
            raise LiveResponseConflict(
                "Assignment-linked reports are not supported until the referenced "
                "deployment assignment can be validated."
            )

        events = self.database["flood_events"]
        teams = self.database["response_teams"]

        event = await events.find_one({"_id": event_id}, session=session)
        if event is None:
            raise LiveResponseNotFound("Flood event not found.")

        team = await teams.find_one({"_id": team_id}, session=session)
        if team is None:
            raise LiveResponseNotFound("Response team not found.")

        now = datetime.now(timezone.utc)
        report_id = str(uuid4())

        report = FieldReport(
            report_id=report_id,
            event_id=event_id,
            team_id=team_id,
            assignment_id=None,
            report_type=report_type,
            title=title,
            description=description,
            location_name=location_name,
            coordinates=coordinates,
            observed_at=observed_at,
            received_at=now,
            status=FieldReportStatus.RECEIVED,
            requires_reassessment=True,
            evidence_reference=evidence_reference,
        )

        # A report is retained as evidence. Subsequent writes may fail, so this
        # multi-document workflow must not be described as transactionally atomic.
        await self.database["field_reports"].insert_one(
            self._document(report, "report_id"), session=session
        )

        locations = await self.database["affected_locations"].find(
            {"event_id": event_id}, session=session
        ).limit(100).to_list(length=100)

        needs = await self.database["resource_needs"].find(
            {"event_id": event_id}, session=session
        ).limit(100).to_list(length=100)

        # These flags request reassessment; they do not constitute a new plan.
        await self.database["affected_locations"].update_many(
            {"event_id": event_id},
            {
                "$set": {
                    "reassessment_required": True,
                    "reassessment_reason": f"Field report {report_id} requires review.",
                    "last_changed_at": now.isoformat(),
                }
            },
            session=session,
        )

        await self.database["resource_needs"].update_many(
            {"event_id": event_id},
            {
                "$set": {
                    "reassessment_required": True,
                    "updated_at": now.isoformat(),
                }
            },
            session=session,
        )

        recommendation_id = str(uuid4())
        recommendation = ReallocationRecommendation(
            recommendation_id=recommendation_id,
            event_id=event_id,
            recommendation_type=self._recommendation_type(report_type),
            status=RecommendationStatus.PROPOSED,
            # This is an initial triage version, not a globally maintained
            # operational-state version. A centralized version store is still
            # needed before recommendations can claim snapshot consistency.
            operational_state_version=1,
            algorithm_version=self.ALGORITHM_VERSION,
            supporting_observation_ids=[],
            supporting_report_ids=[report_id],
            affected_location_ids=[
                str(item.get("_id", item.get("location_id")))
                for item in locations
                if item.get("_id", item.get("location_id")) is not None
            ],
            affected_team_ids=[team_id],
            affected_need_ids=[
                str(item.get("_id", item.get("need_id")))
                for item in needs
                if item.get("_id", item.get("need_id")) is not None
            ],
            summary=f"Review required: {title}",
            rationale=(
                f"Response team {team_id} submitted report {report_id} "
                f"({report_type.value}). This is preliminary triage, not a "
                "verified operational assessment or a newly calculated allocation. "
                "A responsible reviewer must assess the report and current conditions."
            ),
            constraints_or_conflicts=[
                "The report has not been independently verified by this workflow.",
                "No team dispatch or resource reservation has been performed.",
            ],
            unresolved_uncertainties=[
                "The operational state has no centralized version counter yet.",
                "Current team availability and field conditions require review.",
            ],
            created_at=now,
            expires_at=None,
        )

        await self.database["reallocation_recommendations"].insert_one(
            self._document(recommendation, "recommendation_id"), session=session
        )

        report_audit = DecisionAudit(
            audit_id=str(uuid4()),
            event_id=event_id,
            action=DecisionAction.FIELD_REPORT_RECEIVED,
            actor_id=team_id,
            actor_type="RESPONSE_TEAM",
            reason=f"Field report received: {report_id}",
            supporting_evidence_ids=[report_id],
            created_at=now,
        )
        await self.database["decision_audits"].insert_one(
            self._document(report_audit, "audit_id"), session=session
        )

        recommendation_audit = DecisionAudit(
            audit_id=str(uuid4()),
            event_id=event_id,
            action=DecisionAction.RECOMMENDATION_CREATED,
            recommendation_id=recommendation_id,
            actor_id="live-response-triage",
            actor_type="SYSTEM",
            reason=(
                "Created a preliminary recommendation for human review; "
                "no automatic dispatch was performed."
            ),
            supporting_evidence_ids=[report_id],
            created_at=now,
        )
        await self.database["decision_audits"].insert_one(
            self._document(recommendation_audit, "audit_id"), session=session
        )

        return {
            "report": report.model_dump(mode="json"),
            "recommendation": recommendation.model_dump(mode="json"),
            "reassessment_requested": True,
            "dispatch_performed": False,
            "allocation_recalculated": False,
        }

    async def list_reports(
        self, event_id: str, *, limit: int = 20, skip: int = 0
    ) -> list[dict[str, Any]]:
        if await self.database["flood_events"].find_one({"_id": event_id}) is None:
            raise LiveResponseNotFound("Flood event not found.")

        documents = await (
            self.database["field_reports"]
            .find({"event_id": event_id})
            .sort("received_at", -1)
            .skip(skip)
            .limit(limit)
            .to_list(length=limit)
        )
        for document in documents:
            document.pop("_id", None)
        return documents

    async def list_recommendations(
        self, event_id: str, *, limit: int = 20, skip: int = 0
    ) -> list[dict[str, Any]]:
        if await self.database["flood_events"].find_one({"_id": event_id}) is None:
            raise LiveResponseNotFound("Flood event not found.")

        documents = await (
            self.database["reallocation_recommendations"]
            .find({"event_id": event_id})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
            .to_list(length=limit)
        )
        for document in documents:
            document.pop("_id", None)
        return documents
