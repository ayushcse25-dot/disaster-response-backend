"""Seed sample flood events, affected locations, observations and sources.

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
from app.models.enums import (
    EventStatus,
    EventVerificationStatus,
    ObservationType,
    SourceApprovalStatus,
    SourceCategory,
)
from app.models.flood_event import FloodEvent, GeoLocation
from app.models.flood_observation import FloodObservation
from app.models.source import SourceRegistryEntry

SAMPLE_PREFIX = "sample-"
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

    def location(location_id: str, event_id: str, name: str, state: str,
                 severity: SeverityLevel, observation_ids: list[str]) -> AffectedLocation:
        return AffectedLocation(
            location_id=location_id,
            event_id=event_id,
            location_name=name,
            state=state,
            severity=severity,
            supporting_observation_ids=observation_ids,
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

    return {
        "sources": [_doc(s, "source_id") for s in sources],
        "flood_events": [_doc(e, "event_id") for e in events],
        "affected_locations": [_doc(loc, "location_id") for loc in locations],
        "flood_observations": [_doc(o, "observation_id") for o in observations],
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


async def _run() -> int:
    from app.core.config import get_settings
    from app.db.mongo import create_mongo_client

    settings = get_settings()
    client = create_mongo_client(settings)

    try:
        counts = await seed(client[settings.mongodb_db_name])
    except SeedConflictError as exc:
        print(f"Aborted: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    for collection_name, count in counts.items():
        print(f"{collection_name}: {count} sample records upserted")

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
