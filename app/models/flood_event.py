from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    EventStatus,
    EventVerificationStatus,
    HazardType,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GeoLocation(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class FloodEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=100)
    hazard_type: HazardType = HazardType.FLOOD

    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=2000)

    location_name: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    location: GeoLocation | None = None

    status: EventStatus = EventStatus.CANDIDATE
    verification_status: EventVerificationStatus = (
        EventVerificationStatus.UNVERIFIED
    )

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # True only for records written by scripts/seed_sample.py; the API never sets it.
    is_sample: bool = False
    