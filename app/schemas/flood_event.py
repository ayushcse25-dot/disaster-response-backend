from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    EventStatus,
    EventVerificationStatus,
    HazardType,
)
from app.models.affected_location import SeverityLevel
from app.models.flood_event import GeoLocation
from app.services.event_severity import SeverityBasis


class FloodEventCreate(BaseModel):
    """Fields accepted when creating a flood event."""

    model_config = ConfigDict(extra="forbid")

    hazard_type: HazardType = HazardType.FLOOD
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=2000)
    location_name: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    location: GeoLocation | None = None


class FloodEventResponse(BaseModel):
    """Fields returned by the flood-event API."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    hazard_type: HazardType
    title: str
    description: str
    location_name: str
    state: str
    district: str | None
    location: GeoLocation | None
    status: EventStatus
    verification_status: EventVerificationStatus
    created_at: datetime
    updated_at: datetime
    is_sample: bool

    # Derived server-side from affected locations; see app/services/event_severity.py.
    severity: SeverityLevel
    severity_basis: SeverityBasis
