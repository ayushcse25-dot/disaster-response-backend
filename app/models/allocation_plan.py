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
    approval_status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejected_by: str | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
