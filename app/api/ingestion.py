"""Manual ingestion trigger and per-source ingestion status."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pymongo.asynchronous.database import AsyncDatabase

from app.api.auth_deps import require_roles
from app.api.deps import get_database
from app.core.errors import ApiError
from app.models.user import Role
from app.services.ingestion import runner

router = APIRouter(prefix="/api/v1/ingestion", tags=["Ingestion"])
Database = Annotated[AsyncDatabase, Depends(get_database)]


@router.post("/run", dependencies=[Depends(require_roles(Role.AUTHORITY))])
async def run(database: Database) -> dict:
    """Fetch the SACHET feed once. Failures are reported in the status, not raised."""
    try:
        return await runner.run_ingestion(database)
    except runner.IngestionBusy as exc:
        raise ApiError(409, "INGESTION_RUNNING", "An ingestion run is already in progress.") from exc


@router.get("/status")
async def status(database: Database) -> dict:
    """Per source: status, last_success_at, last_error (class only), last_counts."""
    return await runner.get_status(database)
