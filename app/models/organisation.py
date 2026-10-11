"""Responding organisations (NGOs) and their service area."""

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.flood_event import GeoLocation
from app.models.response_team import TeamCapability


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OrganisationStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    SUSPENDED = "SUSPENDED"


class Organisation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organisation_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=2, max_length=200)
    # Short code workers type at login, e.g. "RIVERAID".
    ngo_code: str = Field(min_length=2, max_length=30)
    base_location: GeoLocation | None = None
    service_radius_km: float = Field(default=0, ge=0)
    capabilities: list[TeamCapability] = Field(default_factory=list)
    status: OrganisationStatus = OrganisationStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # True only for records written by scripts/seed_sample.py; the API never sets it.
    is_sample: bool = False
