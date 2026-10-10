from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_database
from app.db.mongo import ping_database
from app.schemas.health import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    """Liveness: the application process is running and serving requests.

    Deliberately does not touch MongoDB, so a database outage never makes
    a platform restart a healthy process.
    """
    return HealthResponse(status="ok", checks={"application": "up"})


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "MongoDB is not reachable."}},
)
async def ready(
    response: Response,
    database: Annotated[AsyncDatabase, Depends(get_database)],
) -> HealthResponse:
    """Readiness: MongoDB answers a ping right now (checked on every request)."""
    if await ping_database(database):
        return HealthResponse(status="ok", checks={"database": "up"})
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="unavailable", checks={"database": "down"})
