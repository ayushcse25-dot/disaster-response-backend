"""Seed sample flood events, locations, observations, sources, resources and plans.

Usage (from the project root, with MONGODB_URI set in the environment or .env):

    python -m scripts.seed_sample --confirm

Safety:
- Refuses to run without --confirm.
- Writes only records whose IDs start with "sample-" and that carry is_sample=true.
- Idempotent: re-running replaces the same sample records instead of adding more.
- If any sample ID is already used by a record that is not sample data, it aborts
  before writing anything. Non-sample records are never modified.
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel

from app.models.affected_location import AffectedLocation, SeverityLevel
from app.models.allocation_plan import AllocationPlanRecord
from app.models.enums import (
    EventStatus,
    EventVerificationStatus,
    ObservationType,
    SourceApprovalStatus,
    SourceCategory,
)
from app.models.flood_event import FloodEvent, GeoLocation
from app.models.flood_observation import FloodObservation
from app.models.organisation import Organisation, OrganisationStatus
from app.models.resource_inventory import (
    InventoryStatus,
    ResourceInventory,
    ResourceType,
)
from app.models.resource_need import NeedStatus, NeedType, NeedUrgency, ResourceNeed
from app.models.response_team import ResponseTeam, TeamCapability, TeamStatus
from app.models.source import SourceRegistryEntry
from app.services.allocation_engine import generate_allocation_plan
from app.services.allocation_plan_service import _planning_snapshot_digest

SAMPLE_PREFIX = "sample-"
SAMPLE_ORGANISATION_ID = "sample-org-001"
LABEL = "SAMPLE DATA — NOT LIVE FLOOD INFORMATION."


class SeedConflictError(RuntimeError):
    """A sample ID is already used by a non-sample record."""


def _doc(model: BaseModel, id_field: str) -> dict[str, Any]:
    document = model.model_dump(mode="json")
    document["_id"] = document.pop(id_field)
    return document


def build_sample_documents(now: datetime) -> dict[str, list[dict[str, Any]]]:
    """Return sample documents per collection, with timestamps relative to now."""

    def ago(**kwargs: float) -> datetime:
        return now - timedelta(**kwargs)

    sources = [
        SourceRegistryEntry(
            source_id="sample-source-gauge",
            name="Sample river gauge feed",
            category=SourceCategory.RIVER_MONITORING,
            approval_status=SourceApprovalStatus.APPROVED,
            description=LABEL,
            access_method="API",
            created_at=ago(days=30),
            updated_at=ago(days=30),
            is_sample=True,
        ),
        SourceRegistryEntry(
            source_id="sample-source-authority",
            name="Sample disaster management bulletin",
            category=SourceCategory.DISASTER_MANAGEMENT,
            approval_status=SourceApprovalStatus.APPROVED,
            description=LABEL,
            access_method="OFFICIAL_FEED",
            created_at=ago(days=30),
            updated_at=ago(days=30),
            is_sample=True,
        ),
        SourceRegistryEntry(
            source_id="sample-source-news",
            name="Sample news wire",
            category=SourceCategory.NEWS_MEDIA,
            approval_status=SourceApprovalStatus.CANDIDATE,
            description=LABEL,
            access_method="RSS",
            created_at=ago(days=30),
            updated_at=ago(days=30),
            is_sample=True,
        ),
    ]

    events = [
        FloodEvent(
            event_id="sample-event-001",
            title="SAMPLE — Riverine flooding near Patna",
            description=LABEL,
            location_name="Patna",
            state="Bihar",
            district="Patna",
            location=GeoLocation(latitude=25.5941, longitude=85.1376),
            status=EventStatus.ACTIVE,
            verification_status=EventVerificationStatus.VERIFIED,
            created_at=ago(hours=30),
            updated_at=ago(minutes=20),
            is_sample=True,
        ),
        FloodEvent(
            event_id="sample-event-002",
            title="SAMPLE — Urban waterlogging in Guwahati",
            description=LABEL,
            location_name="Guwahati",
            state="Assam",
            district="Kamrup Metropolitan",
            location=GeoLocation(latitude=26.1445, longitude=91.7362),
            status=EventStatus.ACTIVE,
            verification_status=EventVerificationStatus.UNDER_REVIEW,
            created_at=ago(hours=10),
            updated_at=ago(hours=2),
            is_sample=True,
        ),
        FloodEvent(
            event_id="sample-event-003",
            title="SAMPLE — Possible flooding reported near Kochi",
            description=LABEL,
            location_name="Kochi",
            state="Kerala",
            district="Ernakulam",
            status=EventStatus.CANDIDATE,
            verification_status=EventVerificationStatus.UNVERIFIED,
            created_at=ago(hours=3),
            updated_at=ago(hours=3),
            is_sample=True,
        ),
    ]

    organisations = [
        Organisation(
            organisation_id=SAMPLE_ORGANISATION_ID, name="SAMPLE River Aid Patna",
            ngo_code="RIVERAID", base_location=GeoLocation(latitude=25.61, longitude=85.10),
            service_radius_km=60, status=OrganisationStatus.APPROVED,
            capabilities=[TeamCapability.WATER_RESCUE, TeamCapability.BOAT_OPERATIONS,
                          TeamCapability.WATER_DISTRIBUTION, TeamCapability.FOOD_DISTRIBUTION,
                          TeamCapability.MEDICAL_AID],
            created_at=ago(days=60), updated_at=ago(days=60), is_sample=True,
        ),
        Organisation(
            organisation_id="sample-org-002", name="SAMPLE Ganga Seva Hajipur",
            ngo_code="GANGASEVA", base_location=GeoLocation(latitude=25.69, longitude=85.21),
            service_radius_km=40, status=OrganisationStatus.APPROVED,
            capabilities=[TeamCapability.FOOD_DISTRIBUTION, TeamCapability.SHELTER_SUPPORT],
            created_at=ago(days=60), updated_at=ago(days=60), is_sample=True,
        ),
        # Out of range for the Patna event (about 650 km away).
        Organisation(
            organisation_id="sample-org-003", name="SAMPLE Brahmaputra Relief Guwahati",
            ngo_code="BRAHMAHELP", base_location=GeoLocation(latitude=26.14, longitude=91.74),
            service_radius_km=50, status=OrganisationStatus.APPROVED,
            capabilities=[TeamCapability.WATER_RESCUE, TeamCapability.SHELTER_SUPPORT],
            created_at=ago(days=60), updated_at=ago(days=60), is_sample=True,
        ),
    ]

    population = {"sample-location-001": 1200, "sample-location-002": 800,
                  "sample-location-004": 300}

    def location(location_id: str, event_id: str, name: str, state: str,
                 severity: SeverityLevel, observation_ids: list[str]) -> AffectedLocation:
        return AffectedLocation(
            location_id=location_id,
            event_id=event_id,
            location_name=name,
            state=state,
            severity=severity,
            supporting_observation_ids=observation_ids,
            population_affected=population.get(location_id),
            assessed_at=ago(hours=1),
            last_changed_at=ago(hours=1),
            reassessment_required=severity == SeverityLevel.UNKNOWN,
            reassessment_reason=LABEL,
            is_sample=True,
        )

    locations = [
        location("sample-location-001", "sample-event-001", "Danapur riverside (sample)",
                 "Bihar", SeverityLevel.CRITICAL, ["sample-obs-001"]),
        location("sample-location-002", "sample-event-001", "Digha ghat (sample)",
                 "Bihar", SeverityLevel.HIGH, ["sample-obs-002"]),
        location("sample-location-003", "sample-event-001", "Phulwari (sample)",
                 "Bihar", SeverityLevel.UNKNOWN, []),
        location("sample-location-004", "sample-event-002", "Anil Nagar (sample)",
                 "Assam", SeverityLevel.MODERATE, ["sample-obs-004"]),
        location("sample-location-005", "sample-event-002", "Zoo Road (sample)",
                 "Assam", SeverityLevel.LOW, []),
    ]

    def observation(observation_id: str, event_id: str, source_id: str,
                    observation_type: ObservationType, title: str, name: str,
                    state: str, observed: datetime,
                    status: EventVerificationStatus) -> FloodObservation:
        return FloodObservation(
            observation_id=observation_id,
            event_id=event_id,
            source_id=source_id,
            observation_type=observation_type,
            title=title,
            description=LABEL,
            location_name=name,
            state=state,
            observed_at=observed,
            received_at=observed + timedelta(minutes=4),
            verification_status=status,
            is_sample=True,
        )

    observations = [
        observation("sample-obs-001", "sample-event-001", "sample-source-gauge",
                    ObservationType.RIVER_LEVEL, "SAMPLE — Gauge above danger level",
                    "Patna", "Bihar", ago(minutes=25), EventVerificationStatus.VERIFIED),
        observation("sample-obs-002", "sample-event-001", "sample-source-authority",
                    ObservationType.SITUATION_REPORT, "SAMPLE — District situation report",
                    "Patna", "Bihar", ago(hours=5), EventVerificationStatus.VERIFIED),
        observation("sample-obs-003", "sample-event-001", "sample-source-news",
                    ObservationType.NEWS_REPORT, "SAMPLE — News report of rising water",
                    "Patna", "Bihar", ago(hours=28), EventVerificationStatus.UNVERIFIED),
        observation("sample-obs-004", "sample-event-002", "sample-source-authority",
                    ObservationType.OBSERVED_INUNDATION, "SAMPLE — Waterlogging observed",
                    "Guwahati", "Assam", ago(hours=2), EventVerificationStatus.UNDER_REVIEW),
        observation("sample-obs-005", "sample-event-003", "sample-source-news",
                    ObservationType.NEWS_REPORT, "SAMPLE — Unconfirmed flooding report",
                    "Kochi", "Kerala", ago(hours=3), EventVerificationStatus.UNVERIFIED),
    ]

    # Check-in ages are chosen so each freshness value appears:
    # inventory interval 24 h, team interval 2 h (see app/services/resource_freshness.py).
    def stock(inventory_id: str, resource_type: ResourceType, name: str, total: float,
              unit: str, verified: datetime | None, confirmed: bool = True) -> ResourceInventory:
        return ResourceInventory(
            inventory_id=inventory_id,
            organisation_id=SAMPLE_ORGANISATION_ID,
            resource_type=resource_type,
            resource_name=name,
            quantity_total=total,
            quantity_unit=unit,
            storage_location="Sample depot, Patna",
            status=InventoryStatus.AVAILABLE if confirmed else InventoryStatus.UNKNOWN,
            availability_confirmed=confirmed,
            last_verified_at=verified,
            created_at=ago(days=7),
            updated_at=verified or ago(days=7),
            is_sample=True,
        )

    inventory = [
        stock("sample-inv-001", ResourceType.BOATS, "SAMPLE inflatable rescue boat",
              4, "boats", ago(hours=2)),                       # FRESH
        stock("sample-inv-002", ResourceType.DRINKING_WATER, "SAMPLE drinking water",
              5000, "litres", ago(hours=20)),                  # DUE
        stock("sample-inv-003", ResourceType.FOOD, "SAMPLE dry ration kits",
              300, "kits", ago(hours=30)),                     # STALE
        stock("sample-inv-004", ResourceType.MEDICAL_KITS, "SAMPLE first aid kits",
              50, "kits", None, confirmed=False),               # UNVERIFIED
    ]

    def team(team_id: str, name: str, capabilities: list[TeamCapability],
             personnel: int, updated: datetime) -> ResponseTeam:
        return ResponseTeam(
            team_id=team_id,
            organisation_id=SAMPLE_ORGANISATION_ID,
            team_name=name,
            capabilities=capabilities,
            personnel_count=personnel,
            status=TeamStatus.AVAILABLE,
            availability_confirmed=True,
            last_status_update=updated,
            created_at=ago(days=7),
            updated_at=updated,
            is_sample=True,
        )

    teams = [
        team("sample-team-001", "SAMPLE boat crew",
             [TeamCapability.WATER_RESCUE, TeamCapability.BOAT_OPERATIONS], 6,
             ago(minutes=20)),                                 # FRESH
        team("sample-team-002", "SAMPLE water distribution team",
             [TeamCapability.WATER_DISTRIBUTION], 4, ago(minutes=100)),   # DUE
        team("sample-team-003", "SAMPLE food distribution team",
             [TeamCapability.FOOD_DISTRIBUTION], 5, ago(hours=5)),        # STALE
    ]

    def need(need_id: str, event_id: str, location_id: str, need_type: NeedType,
             urgency: NeedUrgency, status: NeedStatus, quantity: float,
             unit: str) -> ResourceNeed:
        return ResourceNeed(
            need_id=need_id,
            event_id=event_id,
            location_id=location_id,
            need_type=need_type,
            description=LABEL,
            urgency=urgency,
            status=status,
            quantity_requested=quantity,
            quantity_unit=unit,
            reported_at=ago(hours=3),
            updated_at=ago(hours=1),
            reassessment_required=status != NeedStatus.CONFIRMED,
            is_sample=True,
        )

    needs = [
        need("sample-need-001", "sample-event-001", "sample-location-001", NeedType.RESCUE,
             NeedUrgency.CRITICAL, NeedStatus.CONFIRMED, 2, "boats"),
        need("sample-need-002", "sample-event-001", "sample-location-002",
             NeedType.DRINKING_WATER, NeedUrgency.HIGH, NeedStatus.CONFIRMED, 2000, "litres"),
        need("sample-need-003", "sample-event-001", "sample-location-002", NeedType.FOOD,
             NeedUrgency.MODERATE, NeedStatus.CONFIRMED, 150, "kits"),
        need("sample-need-004", "sample-event-001", "sample-location-001", NeedType.MEDICAL,
             NeedUrgency.HIGH, NeedStatus.REPORTED, 20, "kits"),
        need("sample-need-005", "sample-event-002", "sample-location-004", NeedType.SHELTER,
             NeedUrgency.MODERATE, NeedStatus.REPORTED, 40, "kits"),
    ]

    # Plans come from the real rule-based engine, run over the sample records only.
    def plan(plan_id: str, event: FloodEvent) -> AllocationPlanRecord:
        version = _planning_snapshot_digest(
            event=event, locations=locations, needs=needs, inventory=inventory, teams=teams
        )
        result = generate_allocation_plan(
            event=event, locations=locations, needs=needs, inventory=inventory,
            teams=teams, generated_at=now, inventory_state_version=version,
        )
        result.notes.append(LABEL)
        return AllocationPlanRecord(
            plan_id=plan_id, event_id=event.event_id, plan=result,
            created_at=now, ngo_id=SAMPLE_ORGANISATION_ID, is_sample=True,
        )

    event_by_id = {event.event_id: event for event in events}
    plans = [
        plan("sample-plan-001", event_by_id["sample-event-001"]),   # READY
        plan("sample-plan-002", event_by_id["sample-event-002"]),   # BLOCKED: under review
    ]

    return {
        "organisations": [_doc(o, "organisation_id") for o in organisations],
        "sources": [_doc(s, "source_id") for s in sources],
        "flood_events": [_doc(e, "event_id") for e in events],
        "affected_locations": [_doc(loc, "location_id") for loc in locations],
        "flood_observations": [_doc(o, "observation_id") for o in observations],
        "resource_inventory": [_doc(i, "inventory_id") for i in inventory],
        "response_teams": [_doc(t, "team_id") for t in teams],
        "resource_needs": [_doc(n, "need_id") for n in needs],
        "allocation_plans": [_doc(p, "plan_id") for p in plans],
    }


async def seed(database: Any, now: datetime | None = None) -> dict[str, int]:
    """Upsert the sample documents. Returns the number written per collection."""

    documents = build_sample_documents(now or datetime.now(timezone.utc))

    # Check every collection before writing anything.
    for collection_name, items in documents.items():
        clash = await database[collection_name].find_one(
            {"_id": {"$in": [item["_id"] for item in items]}, "is_sample": {"$ne": True}},
            {"_id": 1},
        )
        if clash is not None:
            raise SeedConflictError(
                f"{collection_name}/{clash['_id']} exists and is not sample data; "
                "nothing was written."
            )

    counts: dict[str, int] = {}

    for collection_name, items in documents.items():
        for item in items:
            # The is_sample filter means a non-sample record can never be replaced:
            # the upsert would fail on the duplicate _id instead.
            await database[collection_name].replace_one(
                {"_id": item["_id"], "is_sample": True},
                item,
                upsert=True,
            )
        counts[collection_name] = len(items)

    return counts


SAMPLE_ACCOUNTS = [
    # (user_id, role, display name, email, ngo_id, worker_id)
    ("sample-user-authority", "AUTHORITY", "SAMPLE District authority",
     "authority@sample.local", None, None),
    ("sample-user-ngo1", "NGO_ADMIN", "SAMPLE River Aid admin",
     "ngo1@sample.local", SAMPLE_ORGANISATION_ID, None),
    ("sample-user-ngo2", "NGO_ADMIN", "SAMPLE Ganga Seva admin",
     "ngo2@sample.local", "sample-org-002", None),
    ("sample-user-worker1", "WORKER", "SAMPLE field worker",
     None, SAMPLE_ORGANISATION_ID, "W-001"),
]


async def seed_accounts(database: Any) -> list[tuple[str, str, str]]:
    """(Re)create the sample accounts with fresh random passwords.

    Returns (role, login, password) for printing; passwords are stored only as hashes.
    """
    import secrets

    from app.core.security import hash_password
    from app.models.user import UserAccount

    credentials = []
    for user_id, role, name, email, ngo_id, worker_id in SAMPLE_ACCOUNTS:
        clash = await database["users"].find_one({"_id": user_id, "is_sample": {"$ne": True}})
        if clash is not None:
            raise SeedConflictError(f"users/{user_id} exists and is not sample data.")
        password = secrets.token_urlsafe(9)
        account = UserAccount(
            user_id=user_id, role=role, display_name=name, email=email, ngo_id=ngo_id,
            worker_id=worker_id, password_hash=hash_password(password), is_sample=True,
        )
        await database["users"].replace_one(
            {"_id": user_id, "is_sample": True}, _doc(account, "user_id"), upsert=True
        )
        login = email or f"ngo_code=RIVERAID worker_id={worker_id}"
        credentials.append((role, login, password))
    return credentials


async def _run() -> int:
    from app.core.config import get_settings
    from app.db.mongo import create_mongo_client

    settings = get_settings()
    client = create_mongo_client(settings)

    try:
        counts = await seed(client[settings.mongodb_db_name])
        credentials = await seed_accounts(client[settings.mongodb_db_name])
    except SeedConflictError as exc:
        print(f"Aborted: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    for collection_name, count in counts.items():
        print(f"{collection_name}: {count} sample records upserted")

    print("\nSample accounts (passwords regenerated on every seed; not stored anywhere else):")
    for role, login, password in credentials:
        print(f"  {role:<10} {login:<40} password: {password}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required. Write sample records to the configured database.",
    )
    args = parser.parse_args(argv)

    if not args.confirm:
        print(
            "Refusing to seed without --confirm. This writes sample records "
            "to the database named by MONGODB_DB_NAME.",
            file=sys.stderr,
        )
        return 2

    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
