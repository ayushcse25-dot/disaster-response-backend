"""Request and response schemas for affected locations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.affected_location import SeverityLevel
from app.models.flood_event import GeoLocation


class AffectedLocationCreate(BaseModel):
    """Validate client input when registering an affected location."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=100)
    location_name: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    coordinates: GeoLocation | None = None

    severity: SeverityLevel = SeverityLevel.UNKNOWN
    supporting_observation_ids: list[str] = Field(default_factory=list)


class AffectedLocationResponse(BaseModel):
    """Represent an affected location returned by the API."""

    model_config = ConfigDict(extra="forbid")

    location_id: str
    event_id: str
    location_name: str
    state: str
    district: str | None
    coordinates: GeoLocation | None

    severity: SeverityLevel
    supporting_observation_ids: list[str]

    assessed_at: datetime
    last_changed_at: datetime
    reassessment_required: bool
    reassessment_reason: str | None
    is_sample: bool
