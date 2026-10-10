from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RecommendationStatus(StrEnum):
    PROPOSED = "PROPOSED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class RecommendationType(StrEnum):
    NEW_ASSIGNMENT = "NEW_ASSIGNMENT"
    REASSIGNMENT = "REASSIGNMENT"
    ADDITIONAL_SUPPORT = "ADDITIONAL_SUPPORT"
    RESOURCE_REALLOCATION = "RESOURCE_REALLOCATION"
    ROUTE_CHANGE = "ROUTE_CHANGE"
    NO_FEASIBLE_ALLOCATION = "NO_FEASIBLE_ALLOCATION"


class ReallocationRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: str = Field(min_length=1, max_length=100)
    event_id: str = Field(min_length=1, max_length=100)

    recommendation_type: RecommendationType
    status: RecommendationStatus = RecommendationStatus.PROPOSED

    # Records the operational state used to calculate this recommendation.
    operational_state_version: int = Field(ge=1)
    algorithm_version: str = Field(min_length=1, max_length=100)

    # References to the evidence and needs relevant to the decision.
    supporting_observation_ids: list[str] = Field(default_factory=list)
    supporting_report_ids: list[str] = Field(default_factory=list)
    affected_location_ids: list[str] = Field(default_factory=list)
    affected_team_ids: list[str] = Field(default_factory=list)
    affected_need_ids: list[str] = Field(default_factory=list)

    summary: str = Field(min_length=1, max_length=1000)
    rationale: str = Field(min_length=1, max_length=5000)

    # Explicitly record problems that prevent a feasible allocation.
    constraints_or_conflicts: list[str] = Field(default_factory=list)
    unresolved_uncertainties: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None

    reviewed_by: str | None = Field(default=None, max_length=100)
    reviewed_at: datetime | None = None
    review_reason: str | None = Field(default=None, max_length=2000)
    