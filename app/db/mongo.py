"""MongoDB connection helpers built on PyMongo's native asynchronous API."""

import asyncio
import logging

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.core.config import Settings

logger = logging.getLogger(__name__)

PING_TIMEOUT_SECONDS = 3.0


def create_mongo_client(settings: Settings) -> AsyncMongoClient:
    """Create the MongoDB client for reuse by the application."""
    try:
        return AsyncMongoClient(
            settings.mongodb_uri.get_secret_value(),
            serverSelectionTimeoutMS=(
                settings.mongodb_server_selection_timeout_ms
            ),
        )
    except PyMongoError as exc:
        logger.error(
            "Invalid MongoDB configuration: %s",
            type(exc).__name__,
        )
        raise RuntimeError(
            "Could not create the MongoDB client; check MONGODB_URI."
        ) from None


async def ping_database(database: AsyncDatabase) -> bool:
    """Return True only if MongoDB answers a ping within the time limit."""
    try:
        async with asyncio.timeout(PING_TIMEOUT_SECONDS):
            await database.command("ping")
    except (PyMongoError, TimeoutError) as exc:
        logger.warning(
            "MongoDB ping failed: %s",
            type(exc).__name__,
        )
        return False

    return True