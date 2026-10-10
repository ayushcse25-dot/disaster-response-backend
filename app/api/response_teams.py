"""API endpoints for response teams."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_database
from app.models.response_team import ResponseTeam
from app.repositories.response_team_repository import ResponseTeamRepository
from app.schemas.response_team import (
    ResponseTeamCreate,
    ResponseTeamLocationUpdate,
    ResponseTeamStatusUpdate,
    ResponseTeamResponse,
)
from app.services.response_team_service import ResponseTeamService


router = APIRouter(tags=["Response Teams"])


def get_response_team_service(
    database=Depends(get_database),
) -> ResponseTeamService:
    """Build the response-team service using the application database."""

    return ResponseTeamService(
        repository=ResponseTeamRepository(database),
    )


@router.post(
    "/api/v1/response-teams",
    response_model=ResponseTeamResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_response_team(
    payload: ResponseTeamCreate,
    service: ResponseTeamService = Depends(get_response_team_service),
) -> ResponseTeamResponse:
    """Register a response team without confirming its availability."""

    team = ResponseTeam(
        team_id=str(uuid4()),
        organisation_id=payload.organisation_id,
        team_name=payload.team_name,
        capabilities=payload.capabilities,
        equipment=payload.equipment,
        personnel_count=payload.personnel_count,
    )

    try:
        created_team = await service.create_team(team)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return ResponseTeamResponse.model_validate(created_team.model_dump())


@router.get(
    "/api/v1/response-teams/{team_id}",
    response_model=ResponseTeamResponse,
)
async def get_response_team(
    team_id: str,
    service: ResponseTeamService = Depends(get_response_team_service),
) -> ResponseTeamResponse:
    """Retrieve a response team by its ID."""

    try:
        team = await service.get_team(team_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Response team '{team_id}' does not exist.",
        )

    return ResponseTeamResponse.model_validate(team.model_dump())


@router.get(
    "/api/v1/organisations/{organisation_id}/response-teams",
    response_model=list[ResponseTeamResponse],
)
async def list_response_teams(
    organisation_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    service: ResponseTeamService = Depends(get_response_team_service),
) -> list[ResponseTeamResponse]:
    """List response teams registered by an organisation."""

    try:
        teams = await service.list_teams_for_organisation(
            organisation_id,
            limit=limit,
            skip=skip,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return [
        ResponseTeamResponse.model_validate(team.model_dump())
        for team in teams
    ]


@router.patch(
    "/api/v1/response-teams/{team_id}/status",
    response_model=ResponseTeamResponse,
)
async def update_response_team_status(
    team_id: str,
    payload: ResponseTeamStatusUpdate,
    service: ResponseTeamService = Depends(get_response_team_service),
) -> ResponseTeamResponse:
    """Record an explicit team status and availability confirmation."""

    try:
        team = await service.update_team_status(
            team_id,
            status=payload.status,
            availability_confirmed=payload.availability_confirmed,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Response team '{team_id}' does not exist.",
        )

    return ResponseTeamResponse.model_validate(team.model_dump())


@router.patch(
    "/api/v1/response-teams/{team_id}/location",
    response_model=ResponseTeamResponse,
)
async def update_response_team_location(
    team_id: str,
    payload: ResponseTeamLocationUpdate,
    service: ResponseTeamService = Depends(get_response_team_service),
) -> ResponseTeamResponse:
    """Update team location without changing operational availability."""

    try:
        team = await service.update_team_location(
            team_id,
            current_location=payload.current_location,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Response team '{team_id}' does not exist.",
        )

    return ResponseTeamResponse.model_validate(team.model_dump())
