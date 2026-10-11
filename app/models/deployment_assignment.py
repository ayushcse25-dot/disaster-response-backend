from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AssignmentStatus(StrEnum):
    RECOMMENDED = "RECOMMENDED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    ASSIGNED = "ASSIGNED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISPATCHED = "DISPATCHED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    # Field task workflow (see app/services/task_service.py).
    PROBLEM = "PROBLEM"
    SUBMITTED = "SUBMITTED"
    NGO_VERIFIED = "NGO_VERIFIED"
    FAILED = "FAILED"


class TaskHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    actor_role: str
    action: str
    from_status: str | None = None
    to_status: str
    note: str | None = None
    at: datetime


class DeploymentAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: str = Field(min_length=1, max_length=100)

    event_id: str = Field(min_length=1, max_length=100)
    location_id: str = Field(min_length=1, max_length=100)
    team_id: str = Field(min_length=1, max_length=100)

    # The task this team is assigned to perform.
    task_description: str = Field(min_length=1, max_length=2000)

    status: AssignmentStatus = AssignmentStatus.RECOMMENDED

    # Preserve the relationship between successive assignment decisions.
    supersedes_assignment_id: str | None = Field(
        default=None,
        max_length=100,
    )

    recommendation_id: str | None = Field(
        default=None,
        max_length=100,
    )

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    approved_by: str | None = Field(default=None, max_length=100)
    approved_at: datetime | None = None

    acknowledged_at: datetime | None = None
    dispatched_at: datetime | None = None
    completed_at: datetime | None = None

    cancellation_reason: str | None = Field(
        default=None,
        max_length=1000,
    )

    # Work-order fields, filled when a plan is approved.
    ngo_id: str | None = Field(default=None, max_length=100)
    need_id: str | None = Field(default=None, max_length=100)
    inventory_id: str | None = Field(default=None, max_length=100)
    quantity: float | None = None
    quantity_unit: str | None = None
    # Account user_id and display worker_id of the assigned field worker.
    worker_user_id: str | None = Field(default=None, max_length=100)
    worker_id: str | None = Field(default=None, max_length=30)
    history: list[TaskHistoryEntry] = Field(default_factory=list)
    # Plain references for now (no upload service yet).
    photo_refs: list[str] = Field(default_factory=list)
    completion_note: str | None = Field(default=None, max_length=2000)
    is_sample: bool = False