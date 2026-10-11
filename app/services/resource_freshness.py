"""Server-side check-in freshness for inventory and response teams.

Rule: check_in_due_at = last check-in + check-in interval, where the interval is
the same maximum age the allocation engine accepts (inventory: last_verified_at
+ 24 h; teams: last_status_update + 2 h).
- FRESH: before the final 25% of the interval.
- DUE: within the final 25% of the interval, before check_in_due_at.
- STALE: at or after check_in_due_at.
- UNVERIFIED: there is no check-in, or it is in the future.

Freshness only describes the age of the last report. Whether a record can be
proposed is reported separately in eligible_for_allocation and status_reason.
"""

from datetime import datetime, timedelta, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.models.resource_inventory import ResourceInventory
from app.models.response_team import ResponseTeam
from app.services.allocation_engine import (
    DEFAULT_INVENTORY_MAX_AGE,
    DEFAULT_TEAM_STATUS_MAX_AGE,
    inventory_ineligibility_reasons,
    team_ineligibility_reasons,
)

DUE_WINDOW_FRACTION = 0.25

FRESHNESS_RULE = (
    "check_in_due_at = last check-in + check_in_interval_hours. FRESH before the "
    "final 25% of the interval, DUE in the final 25%, STALE at or after "
    "check_in_due_at, UNVERIFIED if there is no check-in or it is in the future."
)


class ResourceFreshness(StrEnum):
    FRESH = "FRESH"
    DUE = "DUE"
    STALE = "STALE"
    UNVERIFIED = "UNVERIFIED"


class ResourceStatusFields(BaseModel):
    """Derived fields added to inventory and team responses."""

    model_config = ConfigDict(extra="forbid")

    check_in_due_at: datetime | None
    check_in_interval_hours: float
    freshness: ResourceFreshness
    freshness_rule: str
    eligible_for_allocation: bool
    # Why the record is not eligible, in the backend's words; None when eligible.
    status_reason: str | None


def classify_freshness(
    last_check_in: datetime | None,
    interval: timedelta,
    now: datetime,
) -> tuple[ResourceFreshness, datetime | None]:
    """Apply FRESHNESS_RULE. Returns the freshness and check_in_due_at."""
    if last_check_in is None or last_check_in.tzinfo is None:
        return ResourceFreshness.UNVERIFIED, None

    due_at = last_check_in.astimezone(timezone.utc) + interval

    if last_check_in > now:
        return ResourceFreshness.UNVERIFIED, due_at

    if now >= due_at:
        return ResourceFreshness.STALE, due_at

    if now >= due_at - interval * DUE_WINDOW_FRACTION:
        return ResourceFreshness.DUE, due_at

    return ResourceFreshness.FRESH, due_at


def _fields(
    last_check_in: datetime | None,
    interval: timedelta,
    reasons: list[str],
    now: datetime,
) -> ResourceStatusFields:
    freshness, due_at = classify_freshness(last_check_in, interval, now)

    return ResourceStatusFields(
        check_in_due_at=due_at,
        check_in_interval_hours=interval / timedelta(hours=1),
        freshness=freshness,
        freshness_rule=FRESHNESS_RULE,
        eligible_for_allocation=not reasons,
        status_reason=" ".join(reasons) or None,
    )


def inventory_status_fields(
    item: ResourceInventory,
    now: datetime | None = None,
) -> ResourceStatusFields:
    now = now or datetime.now(timezone.utc)
    return _fields(
        item.last_verified_at,
        DEFAULT_INVENTORY_MAX_AGE,
        inventory_ineligibility_reasons(item, now),
        now,
    )


def team_status_fields(
    team: ResponseTeam,
    now: datetime | None = None,
) -> ResourceStatusFields:
    now = now or datetime.now(timezone.utc)
    return _fields(
        team.last_status_update,
        DEFAULT_TEAM_STATUS_MAX_AGE,
        team_ineligibility_reasons(team, now),
        now,
    )
