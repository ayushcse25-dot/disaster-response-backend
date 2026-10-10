from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.flood_event import GeoLocation


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SeverityLevel(StrEnum):
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AffectedLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str = Field(min_length=1, max_length=100)
    event_id: str = Field(min_length=1, max_length=100)

    location_name: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=100)
    district: str | None = Field(default=None, max_length=100)

    coordinates: GeoLocation | None = None

    # UNKNOWN is used when the available evidence is insufficient.
    severity: SeverityLevel = SeverityLevel.UNKNOWN

    # The source observation IDs supporting the current assessment.
    supporting_observation_ids: list[str] = Field(default_factory=list)

    # When the situation was last assessed and when it last changed.
    assessed_at: datetime = Field(default_factory=utc_now)
    last_changed_at: datetime = Field(default_factory=utc_now)

    # Used to identify locations requiring reassessment.
    reassessment_required: bool = True
    reassessment_reason: str | None = Field(
        default=None,
        max_length=1000,
    )