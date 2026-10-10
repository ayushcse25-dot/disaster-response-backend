"""Tests for the resource inventory service."""

from unittest.mock import AsyncMock

import pytest

from app.models.resource_inventory import (
    InventoryStatus,
    ResourceInventory,
    ResourceType,
)
from app.repositories.resource_inventory_repository import (
    ResourceInventoryRepository,
)
from app.services.resource_inventory_service import (
    ResourceInventoryService,
)


@pytest.fixture
def sample_inventory():
    return ResourceInventory(
        inventory_id="inventory-service-001",
        organisation_id="organisation-001",
        resource_type=ResourceType.DRINKING_WATER,
        resource_name="Drinking water",
        quantity_total=500,
        quantity_reserved=0,
        quantity_deployed=0,
        quantity_unit="litres",
        storage_location="Relief centre A",
        status=InventoryStatus.UNKNOWN,
        availability_confirmed=False,
    )


@pytest.fixture
def service():
    repository = AsyncMock(spec=ResourceInventoryRepository)
    return ResourceInventoryService(repository), repository


@pytest.mark.asyncio
async def test_create_inventory(service, sample_inventory):
    inventory_service, repository = service
    repository.create.return_value = sample_inventory

    result = await inventory_service.create_inventory(sample_inventory)

    assert result == sample_inventory
    repository.create.assert_awaited_once_with(sample_inventory)


@pytest.mark.asyncio
async def test_create_inventory_rejects_confirmed_availability(
    service,
    sample_inventory,
):
    inventory_service, repository = service
    sample_inventory.availability_confirmed = True

    with pytest.raises(ValueError, match="verified through a separate process"):
        await inventory_service.create_inventory(sample_inventory)

    repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_inventory_rejects_non_unknown_status(
    service,
    sample_inventory,
):
    inventory_service, repository = service
    sample_inventory.status = InventoryStatus.AVAILABLE

    with pytest.raises(ValueError, match="must start with UNKNOWN"):
        await inventory_service.create_inventory(sample_inventory)

    repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_inventory_rejects_reserved_stock(
    service,
    sample_inventory,
):
    inventory_service, repository = service
    sample_inventory.quantity_reserved = 10

    with pytest.raises(ValueError, match="cannot start with reserved"):
        await inventory_service.create_inventory(sample_inventory)

    repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_inventory(service, sample_inventory):
    inventory_service, repository = service
    repository.get_by_id.return_value = sample_inventory

    result = await inventory_service.get_inventory(
        sample_inventory.inventory_id
    )

    assert result == sample_inventory
    repository.get_by_id.assert_awaited_once_with(
        sample_inventory.inventory_id
    )


@pytest.mark.asyncio
async def test_get_inventory_rejects_empty_id(service):
    inventory_service, repository = service

    with pytest.raises(ValueError, match="Inventory ID cannot be empty"):
        await inventory_service.get_inventory(" ")

    repository.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_inventory(service, sample_inventory):
    inventory_service, repository = service
    repository.list_by_organisation.return_value = [sample_inventory]

    result = await inventory_service.list_inventory(
        sample_inventory.organisation_id,
        limit=10,
        skip=0,
    )

    assert result == [sample_inventory]
    repository.list_by_organisation.assert_awaited_once_with(
        sample_inventory.organisation_id,
        limit=10,
        skip=0,
    )


@pytest.mark.asyncio
async def test_list_inventory_rejects_empty_organisation(service):
    inventory_service, repository = service

    with pytest.raises(ValueError, match="Organisation ID cannot be empty"):
        await inventory_service.list_inventory(" ")

    repository.list_by_organisation.assert_not_awaited()
