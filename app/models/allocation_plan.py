"""Persisted allocation-plan records."""

from typing import Literal
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field
from app.services.allocation_engine import AllocationPlan


class AllocationPlanRecord(BaseModel):
    """A persisted proposal, not an approved deployment."""
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1, max_length=100)
    event_id: str = Field(min_length=1, max_length=100)
    plan: AllocationPlan
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Per-event plan version; a replan or manual allocation creates version + 1.
    version: int = Field(default=1, ge=1)
    source: Literal["ENGINE", "MANUAL"] = "ENGINE"
    supersedes_plan_id: str | None = None
    superseded_by_plan_id: str | None = None
    created_by: str | None = None
    manual_reason: str | None = Field(default=None, max_length=3000)
    # NGO whose resources this plan uses, when produced by orchestration.
    ngo_id: str | None = None
    # Persisted reasons a replan was requested (e.g. a field worker reported a problem).
    replan_flags: list[str] = Field(default_factory=list)
    approval_status: Literal["PENDING", "APPROVED", "REJECTED", "SUPERSEDED"] = "PENDING"
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejected_by: str | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None

    # True only for records written by scripts/seed_sample.py; the API never sets it.
    is_sample: bool = False


class AllocationPlanView(AllocationPlanRecord):
    """API representation: the stored record plus read-time replan advice."""

    replan_suggested: bool = False
    replan_reasons: list[str] = Field(default_factory=list)
