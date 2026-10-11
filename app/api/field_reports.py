from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_database
from app.models.field_report import FieldReportType
from app.models.flood_event import GeoLocation
from app.services.live_response_service import (
    LiveResponseConflict,
    LiveResponseNotFound,
    LiveResponseService,
)

router = APIRouter(prefix="/api/v1", tags=["Live Response"])


class FieldReportSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: str = Field(min_length=1, max_length=100)
    report_type: FieldReportType
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=3000)
    location_name: str = Field(min_length=1, max_length=200)
    observed_at: datetime
    coordinates: GeoLocation | None = None
    assignment_id: str | None = Field(default=None, max_length=100)
    evidence_reference: str | None = Field(default=None, max_length=500)


def get_live_response_service(
    database: Annotated[AsyncDatabase, Depends(get_database)],
) -> LiveResponseService:
    return LiveResponseService(database)


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, LiveResponseNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, LiveResponseConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc


@router.post(
    "/flood-events/{event_id}/field-reports",
    status_code=status.HTTP_201_CREATED,
)
async def submit_field_report(
    event_id: str,
    request: FieldReportSubmission,
    service: Annotated[LiveResponseService, Depends(get_live_response_service)],
) -> dict[str, Any]:
    try:
        return await service.submit_report(
            event_id,
            team_id=request.team_id,
            report_type=request.report_type,
            title=request.title,
            description=request.description,
            location_name=request.location_name,
            observed_at=request.observed_at,
            coordinates=request.coordinates,
            assignment_id=request.assignment_id,
            evidence_reference=request.evidence_reference,
        )
    except (LiveResponseNotFound, LiveResponseConflict) as exc:
        _raise_http_error(exc)


@router.get("/flood-events/{event_id}/field-reports")
async def list_field_reports(
    event_id: str,
    service: Annotated[LiveResponseService, Depends(get_live_response_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    skip: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    try:
        return await service.list_reports(event_id, limit=limit, skip=skip)
    except LiveResponseNotFound as exc:
        _raise_http_error(exc)


@router.get("/flood-events/{event_id}/reallocation-recommendations")
async def list_reallocation_recommendations(
    event_id: str,
    service: Annotated[LiveResponseService, Depends(get_live_response_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    skip: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    try:
        return await service.list_recommendations(event_id, limit=limit, skip=skip)
    except LiveResponseNotFound as exc:
        _raise_http_error(exc)
