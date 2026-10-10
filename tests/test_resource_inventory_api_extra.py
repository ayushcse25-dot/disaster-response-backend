"""Additional API edge-case tests for resource inventory."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.resource_inventory import get_resource_inventory_service
from app.main import app


@pytest.fixture
def inventory_service_for_edge_tests(client):
    service = AsyncMock()
    app.dependency_overrides[get_resource_inventory_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_resource_inventory_service, None)


@pytest.fixture
def valid_payload():
    return {
        "organisation_id": "NGO-EDGE-001",
        "resource_type": "DRINKING_WATER",
        "resource_name": "Packaged drinking water",
        "quantity_total": 100,
        "quantity_unit": "bottles",
        "storage_location": "Patna warehouse",
    }


@pytest.mark.parametrize(
    "missing_field",
    [
        "organisation_id",
        "resource_type",
        "resource_name",
        "quantity_total",
        "quantity_unit",
        "storage_location",
    ],
)
def test_create_inventory_rejects_each_missing_required_field(
    client, inventory_service_for_edge_tests, valid_payload, missing_field
):
    payload = dict(valid_payload)
    del payload[missing_field]

    response = client.post("/api/v1/resource-inventory", json=payload)

    assert response.status_code == 422
    inventory_service_for_edge_tests.create_inventory.assert_not_awaited()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("organisation_id", " "),
        ("organisation_id", "\t"),
        ("resource_name", "  "),
        ("quantity_unit", " "),
        ("storage_location", "\t"),
    ],
)
def test_create_inventory_rejects_whitespace_only_values(
    client, inventory_service_for_edge_tests, valid_payload, field, value
):
    payload = dict(valid_payload)
    payload[field] = value

    response = client.post("/api/v1/resource-inventory", json=payload)

    assert response.status_code == 422
    inventory_service_for_edge_tests.create_inventory.assert_not_awaited()


@pytest.mark.parametrize("quantity", [-1, -0.1])
def test_create_inventory_rejects_negative_quantity(
    client, inventory_service_for_edge_tests, valid_payload, quantity
):
    payload = dict(valid_payload)
    payload["quantity_total"] = quantity

    response = client.post("/api/v1/resource-inventory", json=payload)

    assert response.status_code == 422
    inventory_service_for_edge_tests.create_inventory.assert_not_awaited()


def test_create_inventory_rejects_boolean_quantity(
    client, inventory_service_for_edge_tests, valid_payload
):
    payload = dict(valid_payload)
    payload["quantity_total"] = True

    response = client.post("/api/v1/resource-inventory", json=payload)

    assert response.status_code == 422
    inventory_service_for_edge_tests.create_inventory.assert_not_awaited()


def test_create_inventory_rejects_unknown_payload_field(
    client, inventory_service_for_edge_tests, valid_payload
):
    payload = dict(valid_payload)
    payload["quantity_reserved"] = 10

    response = client.post("/api/v1/resource-inventory", json=payload)

    assert response.status_code == 422
    inventory_service_for_edge_tests.create_inventory.assert_not_awaited()


def test_create_inventory_rejects_confirmed_availability(
    client, inventory_service_for_edge_tests, valid_payload
):
    payload = dict(valid_payload)
    payload["availability_confirmed"] = True

    response = client.post("/api/v1/resource-inventory", json=payload)

    assert response.status_code == 422
    inventory_service_for_edge_tests.create_inventory.assert_not_awaited()


def test_create_inventory_rejects_non_json_body(
    client, inventory_service_for_edge_tests
):
    response = client.post(
        "/api/v1/resource-inventory",
        content="this is not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    inventory_service_for_edge_tests.create_inventory.assert_not_awaited()


def test_create_inventory_maps_service_value_error_to_conflict(
    client, inventory_service_for_edge_tests, valid_payload
):
    inventory_service_for_edge_tests.create_inventory.side_effect = ValueError(
        "Inventory conflicts with an existing record."
    )

    response = client.post("/api/v1/resource-inventory", json=valid_payload)

    assert response.status_code == 409
    assert "Inventory conflicts" in response.json()["detail"]


def test_get_inventory_maps_blank_id_service_error_to_bad_request(
    client, inventory_service_for_edge_tests
):
    inventory_service_for_edge_tests.get_inventory.side_effect = ValueError(
        "Inventory ID cannot be empty."
    )

    response = client.get("/api/v1/resource-inventory/%20")

    assert response.status_code in (400, 404, 422, 500)


def test_get_inventory_returns_not_found_for_missing_record(
    client, inventory_service_for_edge_tests
):
    inventory_service_for_edge_tests.get_inventory.return_value = None

    response = client.get("/api/v1/resource-inventory/does-not-exist")

    assert response.status_code == 404


def test_list_inventory_rejects_limit_below_minimum(
    client, inventory_service_for_edge_tests
):
    response = client.get(
        "/api/v1/organisations/NGO-EDGE-001/resource-inventory",
        params={"limit": 0, "skip": 0},
    )

    assert response.status_code == 422
    inventory_service_for_edge_tests.list_inventory.assert_not_awaited()


def test_list_inventory_accepts_minimum_limit(
    client, inventory_service_for_edge_tests
):
    inventory_service_for_edge_tests.list_inventory.return_value = []

    response = client.get(
        "/api/v1/organisations/NGO-EDGE-001/resource-inventory",
        params={"limit": 1, "skip": 0},
    )

    assert response.status_code == 200
    assert response.json() == []
    inventory_service_for_edge_tests.list_inventory.assert_awaited_once_with(
        "NGO-EDGE-001", limit=1, skip=0
    )


def test_list_inventory_accepts_maximum_limit(
    client, inventory_service_for_edge_tests
):
    inventory_service_for_edge_tests.list_inventory.return_value = []

    response = client.get(
        "/api/v1/organisations/NGO-EDGE-001/resource-inventory",
        params={"limit": 100, "skip": 0},
    )

    assert response.status_code == 200
    inventory_service_for_edge_tests.list_inventory.assert_awaited_once_with(
        "NGO-EDGE-001", limit=100, skip=0
    )


def test_list_inventory_rejects_limit_above_maximum(
    client, inventory_service_for_edge_tests
):
    response = client.get(
        "/api/v1/organisations/NGO-EDGE-001/resource-inventory",
        params={"limit": 101, "skip": 0},
    )

    assert response.status_code == 422
    inventory_service_for_edge_tests.list_inventory.assert_not_awaited()


def test_list_inventory_rejects_negative_skip(
    client, inventory_service_for_edge_tests
):
    response = client.get(
        "/api/v1/organisations/NGO-EDGE-001/resource-inventory",
        params={"limit": 20, "skip": -1},
    )

    assert response.status_code == 422
    inventory_service_for_edge_tests.list_inventory.assert_not_awaited()


def test_list_inventory_accepts_large_nonnegative_skip(
    client, inventory_service_for_edge_tests
):
    inventory_service_for_edge_tests.list_inventory.return_value = []

    response = client.get(
        "/api/v1/organisations/NGO-EDGE-001/resource-inventory",
        params={"limit": 20, "skip": 100000},
    )

    assert response.status_code == 200
    assert response.json() == []


def test_list_inventory_returns_empty_list_when_no_items_exist(
    client, inventory_service_for_edge_tests
):
    inventory_service_for_edge_tests.list_inventory.return_value = []

    response = client.get(
        "/api/v1/organisations/NGO-EDGE-001/resource-inventory"
    )

    assert response.status_code == 200
    assert response.json() == []


def test_create_inventory_service_error_is_not_misreported_as_success(
    client, inventory_service_for_edge_tests, valid_payload
):
    inventory_service_for_edge_tests.create_inventory.side_effect = RuntimeError(
        "Database operation failed."
    )

    with pytest.raises(RuntimeError):
        client.post("/api/v1/resource-inventory", json=valid_payload)


def test_list_inventory_service_error_is_not_misreported_as_success(
    client, inventory_service_for_edge_tests
):
    inventory_service_for_edge_tests.list_inventory.side_effect = RuntimeError(
        "Database operation failed."
    )

    with pytest.raises(RuntimeError):
        client.get(
            "/api/v1/organisations/NGO-EDGE-001/resource-inventory"
        )
