"""Demo director endpoints. Disabled unless DEMO_ENABLED=true."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pymongo.asynchronous.database import AsyncDatabase

from app.api.allocation_plans import get_allocation_plan_service
from app.api.deps import get_database
from app.core.config import get_settings
from app.core.errors import ApiError
from app.exceptions import PlanningSnapshotError
from app.services import demo_director
from app.services.allocation_plan_service import AllocationPlanService
from app.services.demo_director import DemoError
from app.services.orchestration.run import OrchestrationError
from app.services.plan_lifecycle_service import PlanLifecycleError
from app.services.task_service import TaskError


def require_demo_enabled() -> None:
    if not get_settings().demo_enabled:
        raise ApiError(404, "DEMO_DISABLED", "The demo director is disabled (set DEMO_ENABLED=true).")


router = APIRouter(prefix="/api/v1/demo", tags=["Demo"],
                   dependencies=[Depends(require_demo_enabled)])
Database = Annotated[AsyncDatabase, Depends(get_database)]


@router.post("/reset")
async def reset(database: Database) -> dict:
    """Delete demo-derived sample records and restore the sample seed."""
    return await demo_director.reset(database)


@router.post("/step")
async def step(
    database: Database,
    plan_service: Annotated[AllocationPlanService, Depends(get_allocation_plan_service)],
) -> dict:
    """Advance one scripted step through the real pipeline. Never approves plans."""
    try:
        return await demo_director.step(database, plan_service)
    except DemoError as exc:
        raise ApiError(exc.status_code, exc.code, exc.detail) from exc
    except (OrchestrationError, PlanLifecycleError) as exc:
        raise ApiError(409, exc.code, exc.detail) from exc
    except TaskError as exc:
        raise ApiError(exc.status_code, exc.code, exc.detail) from exc
    except PlanningSnapshotError as exc:
        raise ApiError(503, "SNAPSHOT_UNAVAILABLE", "The planning snapshot could not be loaded.") from exc


@router.get("/state")
async def state(database: Database) -> dict:
    """Current step and the timestamped timeline."""
    return await demo_director.get_state(database)
