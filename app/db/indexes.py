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
    except (PyMongoError, TypeError) as exc:
        logger.warning("Could not ensure indexes: %s", type(exc).__name__)
