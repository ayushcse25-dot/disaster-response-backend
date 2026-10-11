from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionAction(StrEnum):
    RECOMMENDATION_CREATED = "RECOMMENDATION_CREATED"
    RECOMMENDATION_APPROVED = "RECOMMENDATION_APPROVED"
    RECOMMENDATION_REJECTED = "RECOMMENDATION_REJECTED"
    ASSIGNMENT_CREATED = "ASSIGNMENT_CREATED"
    ASSIGNMENT_UPDATED = "ASSIGNMENT_UPDATED"
    ASSIGNMENT_CANCELLED = "ASSIGNMENT_CANCELLED"
    FIELD_REPORT_RECEIVED = "FIELD_REPORT_RECEIVED"
    OPERATIONAL_STATE_UPDATED = "OPERATIONAL_STATE_UPDATED"
    ALLOCATION_FAILED = "ALLOCATION_FAILED"
    NGO_SELECTED = "NGO_SELECTED"
    TASK_UPDATED = "TASK_UPDATED"
    OTHER = "OTHER"


class DecisionAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(min_length=1, max_length=100)
    event_id: str = Field(min_length=1, max_length=100)

    action: DecisionAction

    recommendation_id: str | None = Field(
        default=None,
        max_length=100,
    )
    assignment_id: str | None = Field(
        default=None,
        max_length=100,
    )

    actor_id: str = Field(min_length=1, max_length=100)
    actor_type: str = Field(min_length=1, max_length=50)

    operational_state_version: int | None = Field(
        default=None,
        ge=1,
    )

    reason: str = Field(min_length=1, max_length=3000)

    supporting_evidence_ids: list[str] = Field(
        default_factory=list,
    )

    created_at: datetime = Field(default_factory=utc_now)