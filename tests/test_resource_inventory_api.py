"""API tests for resource inventory."""

from unittest.mock import AsyncMock

import pytest

from app.api.resource_inventory import get_resource_inventory_service
from app.main import app
from app.models.resource_inventory import (
    InventoryStatus,
    ResourceInventory,
    ResourceType,
)


@pytest.fixture
def sample_inventory():
    return ResourceInventory(
        inventory_id="inventory-api-001",
        organisation_id="organisation-api-001",
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
def mock_inventory_service(client):
    service = AsyncMock()
    app.dependency_overrides[get_resource_inventory_service] = (
        lambda: service
    )

    yield service

    app.dependency_overrides.pop(get_resource_inventory_service, None)


def test_create_inventory(client, mock_inventory_service, sample_inventory):
    mock_inventory_service.create_inventory.return_value = sample_inventory

    payload = {
        "organisation_id": sample_inventory.organisation_id,
        "resource_type": "DRINKING_WATER",
        "resource_name": "Drinking water",
        "quantity_total": 500,
        "quantity_unit": "litres",
        "storage_location": "Relief centre A",
    }

    response = client.post("/api/v1/resource-inventory", json=payload)

    assert response.status_code == 201

    body = response.json()
    assert body["inventory_id"] == sample_inventory.inventory_id
    assert body["status"] == "UNKNOWN"
    assert body["availability_confirmed"] is False
    assert body["quantity_reserved"] == 0
    assert body["quantity_deployed"] == 0

    created = mock_inventory_service.create_inventory.await_args.args[0]
    assert created.inventory_id
    assert created.status == InventoryStatus.UNKNOWN
    assert created.availability_confirmed is False


def test_create_inventory_rejects_invalid_resource_type(
    client,
    mock_inventory_service,
):
    payload = {
        "organisation_id": "organisation-api-001",
        "resource_type": "INVALID_TYPE",
        "resource_name": "Drinking water",
        "quantity_total": 500,
        "quantity_unit": "litres",
        "storage_location": "Relief centre A",
    }

    response = client.post("/api/v1/resource-inventory", json=payload)

    assert response.status_code == 422
    mock_inventory_service.create_inventory.assert_not_awaited()


def test_get_inventory(client, mock_inventory_service, sample_inventory):
    mock_inventory_service.get_inventory.return_value = sample_inventory

    response = client.get(
        f"/api/v1/resource-inventory/{sample_inventory.inventory_id}"
    )

    assert response.status_code == 200
    assert response.json()["inventory_id"] == sample_inventory.inventory_id

    mock_inventory_service.get_inventory.assert_awaited_once_with(
        sample_inventory.inventory_id
    )


def test_get_missing_inventory(client, mock_inventory_service):
    mock_inventory_service.get_inventory.return_value = None

    response = client.get("/api/v1/resource-inventory/missing-inventory")

    assert response.status_code == 404


def test_list_inventory(client, mock_inventory_service, sample_inventory):
    mock_inventory_service.list_inventory.return_value = [sample_inventory]

    response = client.get(
        f"/api/v1/organisations/{sample_inventory.organisation_id}/resource-inventory",
        params={"limit": 10, "skip": 0},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["inventory_id"] == sample_inventory.inventory_id

    mock_inventory_service.list_inventory.assert_awaited_once_with(
        sample_inventory.organisation_id,
        limit=10,
        skip=0, include_sample=True,
    )


@pytest.mark.parametrize(
    ("limit", "skip"),
    [
        (0, 0),
        (101, 0),
        (10, -1),
    ],
)
def test_list_inventory_rejects_invalid_pagination(
    client,
    mock_inventory_service,
    limit,
    skip,
):
    response = client.get(
        "/api/v1/organisations/organisation-api-001/resource-inventory",
        params={"limit": limit, "skip": skip},
    )

    assert response.status_code == 422
    mock_inventory_service.list_inventory.assert_not_awaited()
