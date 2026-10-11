"""One ingestion run for the SACHET source, plus per-source status.

Failure behaviour: if the feed cannot be fetched or parsed, nothing is written
except the status record (UNAVAILABLE + error class). Existing observations and
events are never modified or deleted, and nothing is invented.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from xml.etree.ElementTree import ParseError

from pymongo.errors import DuplicateKeyError

from app.models.enums import EventStatus, SourceApprovalStatus, SourceCategory
from app.models.flood_event import FloodEvent
from app.models.source import SourceRegistryEntry
from app.services.ingestion import sachet
from app.services.ingestion.association import candidate_event, match_event
from app.services.ingestion.fetcher import FetchError, fetch_bytes

logger = logging.getLogger(__name__)

STATUS = "ingestion_status"
MAX_ALERTS_PER_RUN = 50
Fetch = Callable[[str], Awaitable[bytes]]

_lock = asyncio.Lock()


class IngestionBusy(Exception):
    pass


SOURCE = SourceRegistryEntry(
    source_id=sachet.SOURCE_ID,
    name="NDMA SACHET CAP alerts (India)",
    category=SourceCategory.DISASTER_MANAGEMENT,
    approval_status=SourceApprovalStatus.APPROVED,
    description=(
        "Common Alerting Protocol alerts from India's National Disaster Management "
        "Authority (IMD, CWC, state SDMAs). RSS marked public domain."
    ),
    website_url=sachet.FEED_URL,
    access_method="RSS",
    is_sample=False,
)


async def ensure_source(database: Any) -> None:
    """Register the source once; an existing registry entry is left as is."""
    document = SOURCE.model_dump(mode="json")
    document["_id"] = document.pop("source_id")
    await database["sources"].update_one(
        {"_id": document["_id"]}, {"$setOnInsert": document}, upsert=True
    )


async def _record_failure(database: Any, error_class: str, now: datetime) -> dict[str, Any]:
    await database[STATUS].update_one(
        {"_id": sachet.SOURCE_ID},
        {"$set": {"status": "UNAVAILABLE", "last_run_at": now.isoformat(),
                  "last_error": error_class, "last_error_at": now.isoformat(),
                  "source_url": sachet.FEED_URL}},
        upsert=True,
    )
    logger.warning("Ingestion failed for %s: %s", sachet.SOURCE_ID, error_class)
    return await get_status(database)


async def _open_events(database: Any) -> list[FloodEvent]:
    documents = await database["flood_events"].find({
        "is_sample": {"$ne": True},
        "status": {"$in": [EventStatus.CANDIDATE.value, EventStatus.ACTIVE.value]},
    }).to_list(length=5000)
    events = []
    for document in documents:
        document["event_id"] = document.pop("_id")
        events.append(FloodEvent.model_validate(document))
    return events


async def run_ingestion(database: Any, *, fetch: Fetch = fetch_bytes) -> dict[str, Any]:
    if _lock.locked():
        raise IngestionBusy()
    async with _lock:
        return await _run(database, fetch)


async def _run(database: Any, fetch: Fetch) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    await ensure_source(database)
    try:
        items = sachet.parse_rss(await fetch(sachet.FEED_URL))
    except FetchError as exc:
        return await _record_failure(database, exc.error_class, now)
    except (ParseError, ValueError) as exc:
        return await _record_failure(database, type(exc).__name__, now)

    counts = {"feed_items": len(items), "flood_candidates": 0, "already_stored": 0,
              "inserted": 0, "not_flood_or_no_location": 0, "failed": 0,
              "events_created": 0, "events_matched": 0}
    candidates = [i for i in items if sachet.is_flood_text(i.title)][:MAX_ALERTS_PER_RUN]
    counts["flood_candidates"] = len(candidates)
    observations = database["flood_observations"]
    last_item_error: str | None = None
    events = await _open_events(database)

    for item in candidates:
        key = sachet.dedupe_key(item)
        if await observations.find_one({"dedupe_key": key}, {"_id": 1}):
            counts["already_stored"] += 1
            continue
        try:
            alert = sachet.parse_cap(await fetch(item.link))
        except FetchError as exc:
            counts["failed"] += 1
            last_item_error = exc.error_class
            continue
        except (ParseError, ValueError) as exc:
            counts["failed"] += 1
            last_item_error = type(exc).__name__
            continue
        observation = sachet.to_observation(item, alert, now) if alert else None
        if observation is None:
            counts["not_flood_or_no_location"] += 1
            continue

        event = match_event(observation, events)
        if event is None:
            event = candidate_event(observation, now)
            document = event.model_dump(mode="json")
            document["_id"] = document.pop("event_id")
            try:
                await database["flood_events"].insert_one(document)
                counts["events_created"] += 1
            except DuplicateKeyError:
                pass
            events.append(event)
        else:
            counts["events_matched"] += 1
        observation.event_id = event.event_id

        document = observation.model_dump(mode="json")
        document["_id"] = document.pop("observation_id")
        try:
            await observations.insert_one(document)
        except DuplicateKeyError:
            counts["already_stored"] += 1
            continue
        counts["inserted"] += 1

        # Extend the association window; never touch status or verification.
        if event.last_observed_at is None or observation.observed_at > event.last_observed_at:
            event.last_observed_at = observation.observed_at
            await database["flood_events"].update_one(
                {"_id": event.event_id},
                {"$set": {"last_observed_at": observation.observed_at.isoformat(),
                          "updated_at": now.isoformat()}},
            )

    degraded = bool(candidates) and counts["failed"] == len(candidates)
    update: dict[str, Any] = {
        "status": "DEGRADED" if degraded else "AVAILABLE",
        "last_run_at": now.isoformat(), "last_counts": counts, "source_url": sachet.FEED_URL,
    }
    if not degraded:
        update["last_success_at"] = now.isoformat()
    if last_item_error:
        update.update(last_error=last_item_error, last_error_at=now.isoformat())
    await database[STATUS].update_one(
        {"_id": sachet.SOURCE_ID},
        {"$set": update, "$inc": {"total_inserted": counts["inserted"]}},
        upsert=True,
    )
    return await get_status(database)


async def get_status(database: Any) -> dict[str, Any]:
    documents = await database[STATUS].find({}).to_list(length=100)
    sources = []
    for document in documents:
        document["source_id"] = document.pop("_id")
        sources.append(document)
    if not any(s["source_id"] == sachet.SOURCE_ID for s in sources):
        sources.append({"source_id": sachet.SOURCE_ID, "status": "NEVER_RUN",
                        "source_url": sachet.FEED_URL})
    return {"sources": sources}


async def ingestion_loop(database: Any, interval_seconds: float) -> None:
    """Background loop (ENV INGESTION_ENABLED=true). Errors are recorded, never raised."""
    while True:
        try:
            await run_ingestion(database)
        except IngestionBusy:
            pass
        except Exception as exc:  # keep the loop alive; status shows the class
            logger.error("Ingestion loop error: %s", type(exc).__name__)
        await asyncio.sleep(interval_seconds)
