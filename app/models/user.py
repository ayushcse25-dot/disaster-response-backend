"""Accounts for staff (authority, NGO admins) and NGO field workers."""

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    AUTHORITY = "AUTHORITY"
    NGO_ADMIN = "NGO_ADMIN"
    WORKER = "WORKER"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class UserAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=100)
    role: Role
    display_name: str = Field(min_length=1, max_length=200)
    # Staff log in with email; workers with ngo_code + worker_id.
    email: str | None = Field(default=None, max_length=200)
    ngo_id: str | None = Field(default=None, max_length=100)
    worker_id: str | None = Field(default=None, max_length=30)
    password_hash: str
    must_change_password: bool = False
    status: AccountStatus = AccountStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_sample: bool = False


class Principal(BaseModel):
    """The authenticated caller, as seen by route handlers."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    role: Role
    display_name: str
    ngo_id: str | None = None
    worker_id: str | None = None
