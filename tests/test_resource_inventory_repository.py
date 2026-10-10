"""Tests for the resource inventory repository."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from app.models.resource_inventory import (
    InventoryStatus,
    ResourceInventory,
    ResourceType,
)
from app.repositories.resource_inventory_repository import (
    ResourceInventoryRepository,
)


@pytest.fixture
def sample_inventory():
    """Create a valid inventory record for testing."""

    now = datetime.now(timezone.utc)

    return ResourceInventory(
        inventory_id="inventory-test-001",
        organisation_id="organisation-test-001",
        resource_type=ResourceType.DRINKING_WATER,
        resource_name="Drinking water",
        quantity_total=500,
        quantity_reserved=0,
        quantity_deployed=0,
        quantity_unit="litres",
        storage_location="Relief centre A",
        status=InventoryStatus.UNKNOWN,
        availability_confirmed=False,
        last_verified_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def repository():
    """Create a repository with a mocked MongoDB collection."""

    database = MagicMock()
    collection = MagicMock()
    database.__getitem__.return_value = collection

    repo = ResourceInventoryRepository(database)
    return repo, collection


@pytest.mark.asyncio
async def test_create_inventory(repository, sample_inventory):
    repo, collection = repository

    collection.insert_one = AsyncMock()

    result = await repo.create(sample_inventory)

    assert result == sample_inventory
    collection.insert_one.assert_awaited_once()

    document = collection.insert_one.await_args.args[0]

    assert document["_id"] == sample_inventory.inventory_id
    assert "inventory_id" not in document
    assert document["quantity_total"] == 500


@pytest.mark.asyncio
async def test_create_duplicate_inventory_id(
    repository,
    sample_inventory,
):
    repo, collection = repository

    collection.insert_one = AsyncMock(
        side_effect=DuplicateKeyError("duplicate key")
    )

    with pytest.raises(ValueError, match="already exists"):
        await repo.create(sample_inventory)


@pytest.mark.asyncio
async def test_get_existing_inventory(repository, sample_inventory):
    repo, collection = repository

    document = sample_inventory.model_dump(mode="json")
    document["_id"] = document.pop("inventory_id")

    collection.find_one = AsyncMock(return_value=document)

    result = await repo.get_by_id(sample_inventory.inventory_id)

    assert result is not None
    assert result.inventory_id == sample_inventory.inventory_id
    assert result.quantity_total == 500

    collection.find_one.assert_awaited_once_with(
        {"_id": sample_inventory.inventory_id}
    )


@pytest.mark.asyncio
async def test_get_missing_inventory(repository):
    repo, collection = repository

    collection.find_one = AsyncMock(return_value=None)

    result = await repo.get_by_id("missing-inventory")

    assert result is None


@pytest.mark.asyncio
async def test_list_inventory_by_organisation(
    repository,
    sample_inventory,
):
    repo, collection = repository

    document = sample_inventory.model_dump(mode="json")
    document["_id"] = document.pop("inventory_id")

    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[document])

    collection.find.return_value = cursor

    result = await repo.list_by_organisation(
        sample_inventory.organisation_id,
        limit=10,
        skip=0,
    )

    assert len(result) == 1
    assert result[0].inventory_id == sample_inventory.inventory_id

    collection.find.assert_called_once_with(
        {"organisation_id": sample_inventory.organisation_id}
    )
    cursor.sort.assert_called_once_with("updated_at", -1)
    cursor.skip.assert_called_once_with(0)
    cursor.limit.assert_called_once_with(10)
    cursor.to_list.assert_awaited_once_with(length=10)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 101])
async def test_list_inventory_rejects_invalid_limit(
    repository,
    limit,
):
    repo, _ = repository

    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        await repo.list_by_organisation(
            "organisation-test-001",
            limit=limit,
        )


@pytest.mark.asyncio
async def test_list_inventory_rejects_negative_skip(repository):
    repo, _ = repository

    with pytest.raises(ValueError, match="skip cannot be negative"):
        await repo.list_by_organisation(
            "organisation-test-001",
            skip=-1,
        )


@pytest.mark.asyncio
async def test_list_inventory_rejects_empty_organisation(repository):
    repo, _ = repository

    with pytest.raises(ValueError, match="Organisation ID cannot be empty"):
        await repo.list_by_organisation("   ")
