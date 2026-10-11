"""Server-side severity rule for a flood event.

Rule: an event's severity is the highest severity among its affected locations
(CRITICAL > HIGH > MODERATE > LOW). Locations still marked UNKNOWN are ignored.
If no location has a known severity, the event severity is UNKNOWN.

Clients must display this value rather than derive their own.
"""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from app.models.affected_location import SeverityLevel

SEVERITY_RULE = (
    "Highest severity among the event's affected locations "
    "(CRITICAL > HIGH > MODERATE > LOW); UNKNOWN locations are ignored; "
    "UNKNOWN when no location has a known severity."
)

_RANK = {
    SeverityLevel.LOW: 1,
    SeverityLevel.MODERATE: 2,
    SeverityLevel.HIGH: 3,
    SeverityLevel.CRITICAL: 4,
}


class SeverityBasis(BaseModel):
    """How the event severity was derived, returned alongside it."""

    model_config = ConfigDict(extra="forbid")

    rule: str
    location_count: int
    assessed_location_count: int


class EventSeverity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: SeverityLevel
    severity_basis: SeverityBasis


def derive_event_severity(levels: Iterable[SeverityLevel]) -> EventSeverity:
    """Apply SEVERITY_RULE to the severities of one event's affected locations."""
    levels = list(levels)
    known = [level for level in levels if level in _RANK]
    severity = max(known, key=_RANK.__getitem__) if known else SeverityLevel.UNKNOWN

    return EventSeverity(
        severity=severity,
        severity_basis=SeverityBasis(
            rule=SEVERITY_RULE,
            location_count=len(levels),
            assessed_location_count=len(known),
        ),
    )
