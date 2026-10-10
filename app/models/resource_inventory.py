from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class ResourceType(StrEnum):
    FOOD = "FOOD"
    DRINKING_WATER = "DRINKING_WATER"
    MEDICAL_KITS = "MEDICAL_KITS"
    BOATS = "BOATS"
    LIFE_JACKETS = "LIFE_JACKETS"
    RESCUE_EQUIPMENT = "RESCUE_EQUIPMENT"
    VEHICLES = "VEHICLES"
    SHELTER_KITS = "SHELTER_KITS"
    SANITATION_KITS = "SANITATION_KITS"
    OTHER = "OTHER"


class InventoryStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    DEPLOYED = "DEPLOYED"
    DEPLETED = "DEPLETED"
    UNAVAILABLE = "UNAVAILABLE"


class ResourceInventory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inventory_id: str = Field(min_length=1, max_length=100)
    organisation_id: str = Field(min_length=1, max_length=100)

    resource_type: ResourceType
    resource_name: str = Field(min_length=2, max_length=200)

    quantity_total: float = Field(ge=0)
    quantity_reserved: float = Field(default=0, ge=0)
    quantity_deployed: float = Field(default=0, ge=0)
    quantity_unit: str = Field(min_length=1, max_length=50)

    storage_location: str = Field(min_length=1, max_length=200)
    status: InventoryStatus = InventoryStatus.UNKNOWN

    availability_confirmed: bool = False
    last_verified_at: datetime | None = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("last_verified_at")
    @classmethod
    def validate_last_verified_at_timezone(
        cls, value: datetime | None
    ) -> datetime | None:
        """Reject verification timestamps without timezone information."""
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError(
                "Timestamp must include timezone information."
            )
        return value

    @model_validator(mode="after")
    def validate_allocated_quantities(self) -> "ResourceInventory":
        """Ensure reserved and deployed stock never exceed total stock."""
        allocated = self.quantity_reserved + self.quantity_deployed

        if allocated > self.quantity_total:
            raise ValueError(
                "Reserved and deployed quantities cannot exceed total quantity."
            )

        return self