"""Run rule-based NGO selection and plan generation for a verified event."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.api.allocation_plans import get_allocation_plan_service
from app.api.deps import get_database
from app.core.errors import ApiError
from app.exceptions import PlanningSnapshotError
from app.services.allocation_plan_service import AllocationPlanService
from app.services.orchestration.run import (
    OrchestrationError,
    OrchestrationResult,
    run_orchestration,
)

router = APIRouter(prefix="/api/v1/orchestration", tags=["Orchestration"])


class OrchestrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=100)


@router.post("/run", response_model=OrchestrationResult)
async def run(
    request: OrchestrationRequest,
    database: Annotated[AsyncDatabase, Depends(get_database)],
    plan_service: Annotated[AllocationPlanService, Depends(get_allocation_plan_service)],
) -> OrchestrationResult:
    """Select an NGO and store a READY plan for human approval. Never approves."""
    try:
        return await run_orchestration(database, plan_service, request.event_id)
    except OrchestrationError as exc:
        status_code = 404 if exc.code == "EVENT_NOT_FOUND" else 422
        raise ApiError(status_code, exc.code, exc.detail) from exc
    except PlanningSnapshotError as exc:
        raise ApiError(503, "SNAPSHOT_UNAVAILABLE", "The planning snapshot could not be loaded completely.") from exc
