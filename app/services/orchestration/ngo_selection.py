"""Choose the NGO to handle an event.

Hard filters first (APPROVED, event inside the service radius), then a weighted
score. Ties break on distance, then organisation_id, so results are deterministic.
"""

from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from pydantic import BaseModel, ConfigDict

from app.models.flood_event import GeoLocation
from app.models.organisation import Organisation, OrganisationStatus
from app.models.resource_inventory import ResourceInventory
from app.models.resource_need import NeedType
from app.models.response_team import ResponseTeam
from app.services.allocation_engine import (
    _NEED_TEAM_CAPABILITIES,
    inventory_ineligibility_reasons,
    team_ineligibility_reasons,
)

WEIGHTS = {"distance": 0.30, "capability": 0.30, "capacity": 0.25, "workload": 0.15}


class NgoCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organisation_id: str
    distance_km: float
    score: float
    components: dict[str, float]
    usable_resources: int
    active_workload: int


class NgoSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected: NgoCandidate | None
    ranked: list[NgoCandidate]
    excluded: dict[str, str]
    explanation: str


def haversine_km(a: GeoLocation, b: GeoLocation) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (a.latitude, a.longitude, b.latitude, b.longitude))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))


def select_ngo(
    *,
    event_location: GeoLocation,
    organisations: list[Organisation],
    inventory: list[ResourceInventory],
    teams: list[ResponseTeam],
    need_types: set[NeedType],
    workload: dict[str, int],
    now: datetime,
) -> NgoSelection:
    excluded: dict[str, str] = {}
    eligible: list[tuple[Organisation, float, int]] = []
    for org in sorted(organisations, key=lambda o: o.organisation_id):
        if org.status != OrganisationStatus.APPROVED:
            excluded[org.organisation_id] = f"Status is {org.status}, not APPROVED."
            continue
        if org.base_location is None:
            excluded[org.organisation_id] = "No base location recorded."
            continue
        distance = haversine_km(event_location, org.base_location)
        if distance > org.service_radius_km:
            excluded[org.organisation_id] = (
                f"Event is {distance:.1f} km away, outside the {org.service_radius_km:g} km service radius."
            )
            continue
        usable = sum(
            1 for i in inventory
            if i.organisation_id == org.organisation_id and not inventory_ineligibility_reasons(i, now)
        ) + sum(
            1 for t in teams
            if t.organisation_id == org.organisation_id and not team_ineligibility_reasons(t, now)
        )
        eligible.append((org, distance, usable))

    max_usable = max((usable for _, _, usable in eligible), default=0)
    ranked: list[NgoCandidate] = []
    for org, distance, usable in eligible:
        org_caps = set(org.capabilities)
        covered = sum(1 for n in need_types if org_caps & _NEED_TEAM_CAPABILITIES[n])
        active = workload.get(org.organisation_id, 0)
        components = {
            "distance": round(1 - distance / org.service_radius_km, 4) if org.service_radius_km else 0.0,
            "capability": round(covered / len(need_types), 4) if need_types else 0.0,
            "capacity": round(usable / max_usable, 4) if max_usable else 0.0,
            "workload": round(1 / (1 + active), 4),
        }
        score = round(sum(WEIGHTS[k] * v for k, v in components.items()), 4)
        ranked.append(NgoCandidate(
            organisation_id=org.organisation_id, distance_km=round(distance, 2), score=score,
            components=components, usable_resources=usable, active_workload=active,
        ))
    ranked.sort(key=lambda c: (-c.score, c.distance_km, c.organisation_id))

    if not ranked:
        explanation = "No NGO passed the hard filters (APPROVED and event within service radius)."
        return NgoSelection(selected=None, ranked=[], excluded=excluded, explanation=explanation)

    top = ranked[0]
    c = top.components
    explanation = (
        f"Selected {top.organisation_id} (score {top.score:.2f}) out of {len(ranked)} eligible NGO(s): "
        f"{top.distance_km:.1f} km from the event (distance {c['distance']:.2f}), "
        f"covers {c['capability']:.0%} of required need types, "
        f"{top.usable_resources} usable resource record(s) (capacity {c['capacity']:.2f}), "
        f"{top.active_workload} active assignment(s) (workload {c['workload']:.2f}). "
        f"Weights: {', '.join(f'{k} {v:g}' for k, v in WEIGHTS.items())}. "
        f"{len(excluded)} NGO(s) excluded by hard filters."
    )
    return NgoSelection(selected=top, ranked=ranked, excluded=excluded, explanation=explanation)
