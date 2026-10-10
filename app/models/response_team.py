from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.flood_event import GeoLocation


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TeamCapability(StrEnum):
    WATER_RESCUE = "WATER_RESCUE"
    BOAT_OPERATIONS = "BOAT_OPERATIONS"
    EVACUATION = "EVACUATION"
    MEDICAL_AID = "MEDICAL_AID"
    FOOD_DISTRIBUTION = "FOOD_DISTRIBUTION"
    WATER_DISTRIBUTION = "WATER_DISTRIBUTION"
    SHELTER_SUPPORT = "SHELTER_SUPPORT"
    TRANSPORT = "TRANSPORT"
    SEARCH_AND_RESCUE = "SEARCH_AND_RESCUE"
    GENERAL_SUPPORT = "GENERAL_SUPPORT"


class TeamStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    AVAILABLE = "AVAILABLE"
    ASSIGNED = "ASSIGNED"
    DEPLOYED = "DEPLOYED"
    UNAVAILABLE = "UNAVAILABLE"
    OFFLINE = "OFFLINE"


class ResponseTeam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: str = Field(min_length=1, max_length=100)
    organisation_id: str = Field(min_length=1, max_length=100)
    team_name: str = Field(min_length=2, max_length=200)

    capabilities: list[TeamCapability] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)

    personnel_count: int = Field(ge=0)
    status: TeamStatus = TeamStatus.UNKNOWN

    current_location: GeoLocation | None = None
    current_assignment_id: str | None = Field(
        default=None,
        max_length=100,
    )

    last_location_update: datetime | None = None
    last_status_update: datetime = Field(default_factory=utc_now)

    # A missing or stale update must not imply availability.
    availability_confirmed: bool = False

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)