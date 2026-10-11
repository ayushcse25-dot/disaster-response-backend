"""API endpoints for resource inventory."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_database
from app.models.resource_inventory import (
    InventoryStatus,
    ResourceInventory,
)
from app.repositories.resource_inventory_repository import (
    ResourceInventoryRepository,
)
from app.schemas.resource_inventory import (
    ResourceInventoryCreate,
    ResourceInventoryResponse,
)
from app.services.resource_freshness import inventory_status_fields
from app.services.resource_inventory_service import (
    ResourceInventoryService,
)


router = APIRouter(tags=["Resource Inventory"])


def to_response(item: ResourceInventory) -> ResourceInventoryResponse:
    """Combine a stored record with its derived freshness and eligibility."""

    return ResourceInventoryResponse.model_validate(
        {**item.model_dump(), **inventory_status_fields(item).model_dump()}
    )


def get_resource_inventory_service(
    database=Depends(get_database),
) -> ResourceInventoryService:
    """Build the inventory service using the application database."""

    repository = ResourceInventoryRepository(database)
    return ResourceInventoryService(repository)


@router.post(
    "/api/v1/resource-inventory",
    response_model=ResourceInventoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_resource_inventory(
    payload: ResourceInventoryCreate,
    service: ResourceInventoryService = Depends(
        get_resource_inventory_service
    ),
) -> ResourceInventoryResponse:
    """Register a new inventory record."""

    inventory = ResourceInventory(
        inventory_id=str(uuid4()),
        organisation_id=payload.organisation_id,
        resource_type=payload.resource_type,
        resource_name=payload.resource_name,
        quantity_total=payload.quantity_total,
        quantity_reserved=0,
        quantity_deployed=0,
        quantity_unit=payload.quantity_unit,
        storage_location=payload.storage_location,
        status=InventoryStatus.UNKNOWN,
        availability_confirmed=False,
    )

    try:
        created = await service.create_inventory(inventory)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return to_response(created)


@router.get(
    "/api/v1/resource-inventory/{inventory_id}",
    response_model=ResourceInventoryResponse,
)
async def get_resource_inventory(
    inventory_id: str,
    service: ResourceInventoryService = Depends(
        get_resource_inventory_service
    ),
) -> ResourceInventoryResponse:
    """Retrieve an inventory record."""

    try:
        inventory = await service.get_inventory(inventory_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if inventory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found.",
        )

    return to_response(inventory)


@router.get(
    "/api/v1/organisations/{organisation_id}/resource-inventory",
    response_model=list[ResourceInventoryResponse],
)
async def list_resource_inventory(
    organisation_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    service: ResourceInventoryService = Depends(
        get_resource_inventory_service
    ),
) -> list[ResourceInventoryResponse]:
    """List inventory records for an organisation."""

    try:
        records = await service.list_inventory(
            organisation_id,
            limit=limit,
            skip=skip,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return [to_response(record) for record in records]
