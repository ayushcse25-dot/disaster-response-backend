"""Attach an ingested observation to an existing flood event, or propose a new one.

Rules (deliberately conservative):
- Only real (non-sample), FLOOD, CANDIDATE or ACTIVE events are considered.
- Same state AND same district, and the observation is within WINDOW of the
  event's last observation. State alone never matches, so unrelated floods in
  one state are not merged.
- Otherwise a new CANDIDATE / UNVERIFIED event is proposed. Nothing is verified here.
"""

import hashlib
from datetime import datetime, timedelta

from app.models.enums import EventStatus, EventVerificationStatus, HazardType
from app.models.flood_event import FloodEvent
from app.models.flood_observation import FloodObservation

WINDOW = timedelta(hours=72)
_OPEN = {EventStatus.CANDIDATE, EventStatus.ACTIVE}


def _same(a: str | None, b: str | None) -> bool:
    return bool(a and b) and " ".join(a.casefold().split()) == " ".join(b.casefold().split())


def match_event(observation: FloodObservation, events: list[FloodEvent]) -> FloodEvent | None:
    if not observation.district:
        return None
    matches = []
    for event in events:
        anchor = event.last_observed_at or event.updated_at
        if (
            not event.is_sample
            and event.hazard_type == HazardType.FLOOD
            and event.status in _OPEN
            and _same(event.state, observation.state)
            and _same(event.district, observation.district)
            and abs(observation.observed_at - anchor) <= WINDOW
        ):
            matches.append(event)
    matches.sort(key=lambda e: (e.last_observed_at or e.updated_at, e.event_id), reverse=True)
    return matches[0] if matches else None


def candidate_event(observation: FloodObservation, now: datetime) -> FloodEvent:
    key = observation.dedupe_key or observation.observation_id
    place = observation.district or observation.location_name
    return FloodEvent(
        event_id="ing-" + hashlib.sha1(key.encode()).hexdigest()[:16],
        title=f"Reported flooding: {place}, {observation.state}"[:200],
        description=(
            "Proposed from an ingested official alert; requires human review. "
            + (observation.summary or "")
        )[:2000],
        location_name=place[:200],
        state=observation.state,
        district=observation.district,
        status=EventStatus.CANDIDATE,
        verification_status=EventVerificationStatus.UNVERIFIED,
        created_at=now,
        updated_at=now,
        last_observed_at=observation.observed_at,
        is_sample=False,
    )
