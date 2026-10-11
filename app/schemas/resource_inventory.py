"""Request and response schemas for resource inventory."""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.services.resource_freshness import ResourceFreshness
from app.models.resource_inventory import (
    InventoryStatus,
    ResourceType,
)


def reject_blank_string(value: str | None) -> str | None:
    """Reject strings that contain only whitespace."""
    if value is not None and not value.strip():
        raise ValueError("Value cannot be blank.")
    return value


class ResourceInventoryCreate(BaseModel):
    """Fields accepted when registering a resource inventory item."""

    model_config = ConfigDict(extra="forbid")

    organisation_id: str = Field(min_length=1, max_length=100)
    resource_type: ResourceType
    resource_name: str = Field(min_length=2, max_length=200)
    quantity_total: float = Field(ge=0)
    quantity_unit: str = Field(min_length=1, max_length=50)
    storage_location: str = Field(min_length=1, max_length=200)
    availability_confirmed: bool = False

    @field_validator("quantity_total", mode="before")
    @classmethod
    def reject_boolean_quantity(cls, value):
        """Reject booleans where a numeric quantity is expected."""
        if isinstance(value, bool):
            raise ValueError("Quantity must be numeric, not boolean.")
        return value

    @field_validator(
        "organisation_id",
        "resource_name",
        "quantity_unit",
        "storage_location",
    )
    @classmethod
    def validate_nonblank_strings(cls, value: str) -> str:
        """Reject strings containing only whitespace."""
        result = reject_blank_string(value)
        assert result is not None
        return result

    @model_validator(mode="after")
    def require_unverified_inventory(self) -> "ResourceInventoryCreate":
        """Require new inventory to be unverified at registration."""
        if self.availability_confirmed:
            raise ValueError(
                "New inventory must be verified through a separate process."
            )
        return self


class ResourceInventoryUpdate(BaseModel):
    """Fields that may be updated for an existing inventory item."""

    model_config = ConfigDict(extra="forbid")

    resource_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=200,
    )
    quantity_total: float | None = Field(default=None, ge=0)
    quantity_unit: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    storage_location: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    status: InventoryStatus | None = None
    availability_confirmed: bool | None = None

    @field_validator("resource_name", "quantity_unit", "storage_location")
    @classmethod
    def validate_nonblank_strings(cls, value: str | None) -> str | None:
        """Reject whitespace-only strings when provided."""
        return reject_blank_string(value)


class ResourceInventoryResponse(BaseModel):
    """Fields returned when reading a resource inventory item."""

    model_config = ConfigDict(extra="forbid")

    inventory_id: str
    organisation_id: str
    resource_type: ResourceType
    resource_name: str
    quantity_total: float
    quantity_reserved: float
    quantity_deployed: float
    quantity_unit: str
    storage_location: str
    status: InventoryStatus
    availability_confirmed: bool
    last_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime
    is_sample: bool

    # Derived server-side; see app/services/resource_freshness.py.
    check_in_due_at: datetime | None
    check_in_interval_hours: float
    freshness: ResourceFreshness
    freshness_rule: str
    eligible_for_allocation: bool
    status_reason: str | None
