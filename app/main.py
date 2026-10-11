"""Application entry point. Run with: uvicorn app.main:app --reload"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.api import (
    allocation_plans,
    auth,
    affected_locations,
    flood_events,
    flood_observations,
    health,
    orchestration,
    resource_inventory,
    resource_needs,
    response_teams,
    field_reports,
)
from app.api.auth_deps import STAFF, require_roles
from app.core.config import get_settings
from app.models.user import Role
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.db.indexes import ensure_indexes
from app.db.mongo import create_mongo_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create one MongoDB client at startup and close it at shutdown."""

    settings = get_settings()
    configure_logging(settings.log_level)
    client = create_mongo_client(settings)
    app.state.mongo_db = client[settings.mongodb_db_name]
    # In the background so an unreachable database never delays startup.
    index_task = asyncio.create_task(ensure_indexes(app.state.mongo_db))
    logger.info("Application started (environment=%s)", settings.environment)
    try:
        yield
    finally:
        index_task.cancel()
        await client.close()
        logger.info("MongoDB client closed")


def create_app() -> FastAPI:
    app = FastAPI(title="Disaster Response Platform API", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    # Every other router requires a signed-in staff account; individual routes
    # add NGO scope checks. Workers only reach /me and their tasks.
    staff = [Depends(require_roles(*STAFF))]
    for module in (
        allocation_plans, flood_events, flood_observations, resource_needs,
        resource_inventory, affected_locations, response_teams, field_reports,
    ):
        app.include_router(module.router, dependencies=staff)
    app.include_router(
        orchestration.router, dependencies=[Depends(require_roles(Role.AUTHORITY))]
    )
    return app


app = create_app()
