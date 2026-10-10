from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models.enums import ObservationType, EventVerificationStatus


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class FloodObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str = Field(min_length=1, max_length=100)

    # The associated flood event, if one has been identified.
    event_id: str | None = Field(default=None, max_length=100)

    source_id: str = Field(min_length=1, max_length=100)
    observation_type: ObservationType

    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=1, max_length=5000)

    location_name: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=100)
    district: str | None = Field(default=None, max_length=100)

    # When the reported situation was observed or the information was published.
    observed_at: datetime

    # When our system received the information.
    received_at: datetime = Field(default_factory=utc_now)

    source_url: HttpUrl | None = None

    # Preserve the original claim separately from our assessment.
    verification_status: EventVerificationStatus = (
        EventVerificationStatus.UNVERIFIED
    )

    # Original source material or a reference to securely stored evidence.
    evidence_reference: str | None = Field(
        default=None,
        max_length=500,
    )

    @field_validator("observed_at", "received_at")
    @classmethod
    def validate_timezone_aware_timestamp(cls, value: datetime) -> datetime:
        """Reject timestamps that do not contain timezone information."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must include timezone information.")

        return value