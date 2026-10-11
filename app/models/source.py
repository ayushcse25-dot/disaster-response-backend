from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.enums import SourceApprovalStatus, SourceCategory


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SourceRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=2, max_length=200)

    category: SourceCategory
    approval_status: SourceApprovalStatus = SourceApprovalStatus.CANDIDATE

    description: str = Field(default="", max_length=1000)

    website_url: HttpUrl | None = None

    # Examples: API, RSS, OFFICIAL_FEED, FIELD_REPORT
    access_method: str = Field(min_length=2, max_length=50)

    # The source must be reviewed before being used for operational decisions.
    reviewed_by: str | None = Field(default=None, max_length=100)
    reviewed_at: datetime | None = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # True only for records written by scripts/seed_sample.py; the API never sets it.
    is_sample: bool = False
