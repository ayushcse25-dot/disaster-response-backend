from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class NeedType(StrEnum):
    RESCUE = "RESCUE"
    EVACUATION = "EVACUATION"
    FOOD = "FOOD"
    DRINKING_WATER = "DRINKING_WATER"
    MEDICAL = "MEDICAL"
    SHELTER = "SHELTER"
    TRANSPORT = "TRANSPORT"
    SANITATION = "SANITATION"
    OTHER = "OTHER"


class NeedUrgency(StrEnum):
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NeedStatus(StrEnum):
    REPORTED = "REPORTED"
    UNDER_ASSESSMENT = "UNDER_ASSESSMENT"
    CONFIRMED = "CONFIRMED"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    FULFILLED = "FULFILLED"
    REJECTED = "REJECTED"


class ResourceNeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    need_id: str = Field(min_length=1, max_length=100)
    event_id: str = Field(min_length=1, max_length=100)
    location_id: str = Field(min_length=1, max_length=100)

    need_type: NeedType
    description: str = Field(min_length=1, max_length=2000)

    urgency: NeedUrgency = NeedUrgency.UNKNOWN
    status: NeedStatus = NeedStatus.REPORTED

    # Quantity must use a clearly defined unit.
    quantity_requested: float | None = Field(default=None, gt=0)
    quantity_unit: str | None = Field(default=None, max_length=50)
    quantity_fulfilled: float = Field(default=0, ge=0)

    supporting_observation_ids: list[str] = Field(default_factory=list)

    reported_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    reassessment_required: bool = True

    @model_validator(mode="after")
    def validate_fulfilled_quantity(self) -> "ResourceNeed":
        """Prevent fulfilled quantity from exceeding a known requested quantity."""
        if (
            self.quantity_requested is not None
            and self.quantity_fulfilled > self.quantity_requested
        ):
            raise ValueError(
                "Fulfilled quantity cannot exceed requested quantity."
            )

        return self