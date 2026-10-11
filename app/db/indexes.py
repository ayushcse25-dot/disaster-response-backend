"""Indexes the application relies on for correctness (not just speed)."""

import logging

from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)


async def ensure_indexes(database) -> None:
    """Create required indexes; log and continue if the database is unreachable."""
    try:
        # One plan per (event, version): concurrent replans cannot both win.
        await database["allocation_plans"].create_index(
            [("event_id", 1), ("version", 1)],
            unique=True,
            name="event_version_unique",
            partialFilterExpression={"version": {"$exists": True}},
        )
        # One orchestration result per (event, input snapshot): reruns are idempotent.
        await database["ngo_assignments"].create_index(
            [("event_id", 1), ("input_digest", 1)], unique=True, name="event_digest_unique"
        )
        await database["users"].create_index(
            "email", unique=True, name="email_unique",
            partialFilterExpression={"email": {"$type": "string"}},
        )
        await database["users"].create_index(
            [("ngo_id", 1), ("worker_id", 1)], unique=True, name="ngo_worker_unique",
            partialFilterExpression={"worker_id": {"$type": "string"}},
        )
        # Ingested items: one observation per source item, so reruns never duplicate.
        await database["flood_observations"].create_index(
            "dedupe_key", unique=True, name="dedupe_key_unique",
            partialFilterExpression={"dedupe_key": {"$type": "string"}},
        )
    except (PyMongoError, TypeError) as exc:
        logger.warning("Could not ensure indexes: %s", type(exc).__name__)
