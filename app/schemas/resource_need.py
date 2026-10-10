"""Request and response schemas for resource needs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.resource_need import (
    NeedType,
    NeedUrgency,
    NeedStatus,
)


class ResourceNeedCreate(BaseModel):
    """Validate client input when reporting a resource need."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=100)
    location_id: str = Field(min_length=1, max_length=100)

    need_type: NeedType
    description: str = Field(min_length=1, max_length=2000)

    urgency: NeedUrgency = NeedUrgency.UNKNOWN

    quantity_requested: float | None = Field(default=None, gt=0)
    quantity_unit: str | None = Field(default=None, max_length=50)

    supporting_observation_ids: list[str] = Field(default_factory=list)


class ResourceNeedResponse(BaseModel):
    """Represent a resource need returned by the API."""

    model_config = ConfigDict(extra="forbid")

    need_id: str
    event_id: str
    location_id: str

    need_type: NeedType
    description: str

    urgency: NeedUrgency
    status: NeedStatus

    quantity_requested: float | None
    quantity_unit: str | None
    quantity_fulfilled: float

    supporting_observation_ids: list[str]

    reported_at: datetime
    updated_at: datetime

    reassessment_required: bool