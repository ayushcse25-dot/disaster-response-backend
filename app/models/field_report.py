from datetime import datetime, timezone
from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.models.flood_event import GeoLocation


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class FieldReportType(StrEnum):
    SITUATION_UPDATE = "SITUATION_UPDATE"
    WATER_LEVEL_CHANGE = "WATER_LEVEL_CHANGE"
    ROAD_BLOCKED = "ROAD_BLOCKED"
    ROAD_ACCESS_RESTORED = "ROAD_ACCESS_RESTORED"
    NEW_RESCUE_NEED = "NEW_RESCUE_NEED"
    RESOURCE_SHORTAGE = "RESOURCE_SHORTAGE"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_COMPLETED = "TASK_COMPLETED"
    TEAM_UNAVAILABLE = "TEAM_UNAVAILABLE"
    EQUIPMENT_FAILURE = "EQUIPMENT_FAILURE"
    MEDICAL_EMERGENCY = "MEDICAL_EMERGENCY"
    OTHER = "OTHER"


class FieldReportStatus(StrEnum):
    RECEIVED = "RECEIVED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class FieldReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1, max_length=100)

    event_id: str = Field(min_length=1, max_length=100)
    team_id: str = Field(min_length=1, max_length=100)

    assignment_id: str | None = Field(
        default=None,
        max_length=100,
    )

    report_type: FieldReportType

    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=1, max_length=5000)

    location_name: str = Field(min_length=1, max_length=200)
    coordinates: GeoLocation | None = None

    # When the team observed the reported condition.
    observed_at: datetime

    # When the backend received the report.
    received_at: datetime = Field(default_factory=utc_now)

    status: FieldReportStatus = Field(
        default=FieldReportStatus.RECEIVED
    )

    requires_reassessment: bool = True

    # Optional reference to supporting evidence.
    evidence_reference: str | None = Field(
        default=None,
        max_length=500,
    )

    @field_validator("observed_at", "received_at")
    @classmethod
    def validate_timezone_aware_timestamp(
        cls,
        value: datetime,
    ) -> datetime:
        """Reject timestamps that do not contain timezone information."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Timestamp must include timezone information."
            )

        return value