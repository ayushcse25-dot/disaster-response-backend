"""Response schemas for flood observations."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, HttpUrl

from app.models.enums import (
    EventVerificationStatus,
    ObservationType,
    SourceApprovalStatus,
    SourceCategory,
)


class Freshness(StrEnum):
    """Age of an observation at request time; see FRESHNESS_RULE."""

    FRESH = "FRESH"
    RECENT = "RECENT"
    STALE = "STALE"


FRESHNESS_RULE = (
    "Age of observed_at at request time: FRESH under 1 hour, "
    "RECENT under 24 hours, STALE otherwise."
)


class FloodObservationResponse(BaseModel):
    """An observation with its source name joined from the source registry.

    evidence_reference is deliberately not returned: it can point to
    securely stored material.
    """

    model_config = ConfigDict(extra="forbid")

    observation_id: str
    event_id: str | None
    source_id: str
    # None when the source is missing from the registry.
    source_name: str | None
    source_category: SourceCategory | None
    source_approval_status: SourceApprovalStatus | None
    observation_type: ObservationType
    title: str
    description: str
    location_name: str
    state: str
    district: str | None
    # When the situation was observed or published at the source.
    observed_at: datetime
    # When our system retrieved it.
    received_at: datetime
    source_url: HttpUrl | None
    verification_status: EventVerificationStatus
    freshness: Freshness
    freshness_rule: str
    is_sample: bool
