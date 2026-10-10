"""Request and response schemas for response teams."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.flood_event import GeoLocation
from app.models.response_team import TeamCapability, TeamStatus


class ResponseTeamCreate(BaseModel):
    """Validate client input when registering a response team."""

    model_config = ConfigDict(extra="forbid")

    organisation_id: str = Field(min_length=1, max_length=100)
    team_name: str = Field(min_length=2, max_length=200)
    capabilities: list[TeamCapability] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    personnel_count: int = Field(ge=0)


class ResponseTeamStatusUpdate(BaseModel):
    """Explicitly report operational status and availability."""

    model_config = ConfigDict(extra="forbid")

    status: TeamStatus
    availability_confirmed: bool

    @model_validator(mode="after")
    def validate_availability(self):
        if self.status in {TeamStatus.ASSIGNED, TeamStatus.DEPLOYED}:
            raise ValueError(
                "Assignment and deployment status must be managed by the "
                "assignment workflow."
            )

        if self.status == TeamStatus.AVAILABLE and not self.availability_confirmed:
            raise ValueError(
                "AVAILABLE status requires explicit availability confirmation."
            )

        if self.status in {
            TeamStatus.UNKNOWN,
            TeamStatus.UNAVAILABLE,
            TeamStatus.OFFLINE,
        } and self.availability_confirmed:
            raise ValueError(
                "This status cannot be marked as availability-confirmed."
            )

        return self


class ResponseTeamLocationUpdate(BaseModel):
    """Report a team's current location."""

    model_config = ConfigDict(extra="forbid")

    current_location: GeoLocation


class ResponseTeamResponse(BaseModel):
    """Represent a response team returned by the API."""

    model_config = ConfigDict(extra="forbid")

    team_id: str
    organisation_id: str
    team_name: str
    capabilities: list[TeamCapability]
    equipment: list[str]
    personnel_count: int
    status: TeamStatus
    current_location: GeoLocation | None
    current_assignment_id: str | None
    last_location_update: datetime | None
    last_status_update: datetime
    availability_confirmed: bool
    created_at: datetime
    updated_at: datetime
