"""Additional validation tests for resource inventory."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.models.resource_inventory import (
    InventoryStatus,
    ResourceInventory,
    ResourceType,
)
from app.schemas.resource_inventory import (
    ResourceInventoryCreate,
    ResourceInventoryUpdate,
)


@pytest.fixture
def valid_inventory_payload():
    return {
        "organisation_id": "NGO-TEST-001",
        "resource_type": "DRINKING_WATER",
        "resource_name": "Packaged drinking water",
        "quantity_total": 500,
        "quantity_unit": "bottles",
        "storage_location": "Patna Relief Warehouse",
        "availability_confirmed": False,
    }


@pytest.fixture
def valid_inventory_model_data():
    return {
        "inventory_id": "inventory-validation-001",
        "organisation_id": "NGO-TEST-001",
        "resource_type": ResourceType.DRINKING_WATER,
        "resource_name": "Packaged drinking water",
        "quantity_total": 100,
        "quantity_reserved": 0,
        "quantity_deployed": 0,
        "quantity_unit": "bottles",
        "storage_location": "Patna Relief Warehouse",
        "status": InventoryStatus.UNKNOWN,
        "availability_confirmed": False,
    }


def test_create_schema_accepts_valid_payload(valid_inventory_payload):
    result = ResourceInventoryCreate.model_validate(valid_inventory_payload)
    assert result.organisation_id == "NGO-TEST-001"
    assert result.resource_type == ResourceType.DRINKING_WATER


@pytest.mark.parametrize(
    "organisation_id",
    ["", " ", "\t", "\n"],
)
def test_create_schema_rejects_blank_organisation_id(
    valid_inventory_payload, organisation_id
):
    payload = deepcopy(valid_inventory_payload)
    payload["organisation_id"] = organisation_id

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


@pytest.mark.parametrize(
    "organisation_id",
    ["N" * 101],
)
def test_create_schema_rejects_oversized_organisation_id(
    valid_inventory_payload, organisation_id
):
    payload = deepcopy(valid_inventory_payload)
    payload["organisation_id"] = organisation_id

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


@pytest.mark.parametrize(
    "resource_name",
    ["", "A", " "],
)
def test_create_schema_rejects_short_resource_name(
    valid_inventory_payload, resource_name
):
    payload = deepcopy(valid_inventory_payload)
    payload["resource_name"] = resource_name

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


def test_create_schema_rejects_oversized_resource_name(
    valid_inventory_payload,
):
    payload = deepcopy(valid_inventory_payload)
    payload["resource_name"] = "W" * 201

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


@pytest.mark.parametrize("quantity", [-1, -0.01, -100])
def test_create_schema_rejects_negative_quantity(
    valid_inventory_payload, quantity
):
    payload = deepcopy(valid_inventory_payload)
    payload["quantity_total"] = quantity

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


@pytest.mark.parametrize("quantity", [0, 0.0, 1, 100, 500.5])
def test_create_schema_accepts_nonnegative_quantity(
    valid_inventory_payload, quantity
):
    payload = deepcopy(valid_inventory_payload)
    payload["quantity_total"] = quantity

    result = ResourceInventoryCreate.model_validate(payload)
    assert result.quantity_total == quantity


@pytest.mark.parametrize(
    "quantity_unit",
    ["", " ", "\t"],
)
def test_create_schema_rejects_blank_quantity_unit(
    valid_inventory_payload, quantity_unit
):
    payload = deepcopy(valid_inventory_payload)
    payload["quantity_unit"] = quantity_unit

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


def test_create_schema_rejects_oversized_quantity_unit(
    valid_inventory_payload,
):
    payload = deepcopy(valid_inventory_payload)
    payload["quantity_unit"] = "u" * 51

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


@pytest.mark.parametrize(
    "storage_location",
    ["", " ", "\t"],
)
def test_create_schema_rejects_blank_storage_location(
    valid_inventory_payload, storage_location
):
    payload = deepcopy(valid_inventory_payload)
    payload["storage_location"] = storage_location

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


def test_create_schema_rejects_oversized_storage_location(
    valid_inventory_payload,
):
    payload = deepcopy(valid_inventory_payload)
    payload["storage_location"] = "L" * 201

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


@pytest.mark.parametrize(
    "resource_type",
    ["WATER", "INVALID", "", "food"],
)
def test_create_schema_rejects_unknown_resource_type(
    valid_inventory_payload, resource_type
):
    payload = deepcopy(valid_inventory_payload)
    payload["resource_type"] = resource_type

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


def test_create_schema_rejects_client_confirmed_availability(
    valid_inventory_payload,
):
    payload = deepcopy(valid_inventory_payload)
    payload["availability_confirmed"] = True

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


def test_create_schema_rejects_unexpected_fields(valid_inventory_payload):
    payload = deepcopy(valid_inventory_payload)
    payload["quantity_reserved"] = 10

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


def test_create_schema_rejects_missing_organisation_id(valid_inventory_payload):
    payload = deepcopy(valid_inventory_payload)
    del payload["organisation_id"]

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


def test_create_schema_rejects_missing_resource_type(valid_inventory_payload):
    payload = deepcopy(valid_inventory_payload)
    del payload["resource_type"]

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


def test_create_schema_rejects_missing_resource_name(valid_inventory_payload):
    payload = deepcopy(valid_inventory_payload)
    del payload["resource_name"]

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


def test_create_schema_rejects_missing_quantity(valid_inventory_payload):
    payload = deepcopy(valid_inventory_payload)
    del payload["quantity_total"]

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


def test_create_schema_rejects_missing_quantity_unit(valid_inventory_payload):
    payload = deepcopy(valid_inventory_payload)
    del payload["quantity_unit"]

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


def test_create_schema_rejects_missing_storage_location(valid_inventory_payload):
    payload = deepcopy(valid_inventory_payload)
    del payload["storage_location"]

    with pytest.raises(ValidationError):
        ResourceInventoryCreate.model_validate(payload)


def test_inventory_model_accepts_zero_total(valid_inventory_model_data):
    data = deepcopy(valid_inventory_model_data)
    data["quantity_total"] = 0

    inventory = ResourceInventory.model_validate(data)
    assert inventory.quantity_total == 0


@pytest.mark.parametrize(
    ("reserved", "deployed"),
    [
        (0, 0),
        (100, 0),
        (0, 100),
        (40, 60),
        (25.5, 24.5),
    ],
)
def test_inventory_model_accepts_allocations_within_total(
    valid_inventory_model_data, reserved, deployed
):
    data = deepcopy(valid_inventory_model_data)
    data["quantity_reserved"] = reserved
    data["quantity_deployed"] = deployed

    inventory = ResourceInventory.model_validate(data)
    assert inventory.quantity_reserved + inventory.quantity_deployed <= (
        inventory.quantity_total
    )


@pytest.mark.parametrize(
    ("reserved", "deployed"),
    [
        (101, 0),
        (0, 101),
        (60, 41),
        (50.5, 50),
    ],
)
def test_inventory_model_rejects_allocations_above_total(
    valid_inventory_model_data, reserved, deployed
):
    data = deepcopy(valid_inventory_model_data)
    data["quantity_reserved"] = reserved
    data["quantity_deployed"] = deployed

    with pytest.raises(ValidationError):
        ResourceInventory.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity_total", -1),
        ("quantity_reserved", -1),
        ("quantity_deployed", -1),
    ],
)
def test_inventory_model_rejects_negative_quantities(
    valid_inventory_model_data, field, value
):
    data = deepcopy(valid_inventory_model_data)
    data[field] = value

    with pytest.raises(ValidationError):
        ResourceInventory.model_validate(data)


def test_inventory_model_rejects_unknown_status(valid_inventory_model_data):
    data = deepcopy(valid_inventory_model_data)
    data["status"] = "MAGICALLY_AVAILABLE"

    with pytest.raises(ValidationError):
        ResourceInventory.model_validate(data)


def test_inventory_model_rejects_unknown_resource_type(
    valid_inventory_model_data,
):
    data = deepcopy(valid_inventory_model_data)
    data["resource_type"] = "UNKNOWN_RESOURCE"

    with pytest.raises(ValidationError):
        ResourceInventory.model_validate(data)


def test_inventory_model_rejects_unexpected_fields(valid_inventory_model_data):
    data = deepcopy(valid_inventory_model_data)
    data["unreviewed"] = True

    with pytest.raises(ValidationError):
        ResourceInventory.model_validate(data)


def test_update_schema_accepts_valid_partial_update():
    update = ResourceInventoryUpdate.model_validate(
        {"resource_name": "Emergency water supply"}
    )

    assert update.resource_name == "Emergency water supply"


def test_update_schema_accepts_empty_partial_update():
    update = ResourceInventoryUpdate.model_validate({})
    assert update.model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize(
    "quantity",
    [-1, -0.1],
)
def test_update_schema_rejects_negative_quantity(quantity):
    with pytest.raises(ValidationError):
        ResourceInventoryUpdate.model_validate({"quantity_total": quantity})


@pytest.mark.parametrize(
    "resource_name",
    ["", "A", " "],
)
def test_update_schema_rejects_invalid_resource_name(resource_name):
    with pytest.raises(ValidationError):
        ResourceInventoryUpdate.model_validate(
            {"resource_name": resource_name}
        )


def test_update_schema_rejects_unexpected_fields():
    with pytest.raises(ValidationError):
        ResourceInventoryUpdate.model_validate({"organisation_id": "NGO-NEW"})


@pytest.mark.parametrize(
    "status",
    ["AVAILABLE", "RESERVED", "DEPLOYED", "DEPLETED", "UNAVAILABLE", "UNKNOWN"],
)
def test_update_schema_accepts_defined_statuses(status):
    update = ResourceInventoryUpdate.model_validate({"status": status})
    assert update.status == InventoryStatus(status)


def test_update_schema_rejects_unknown_status():
    with pytest.raises(ValidationError):
        ResourceInventoryUpdate.model_validate({"status": "READY_FOR_ANYTHING"})


def test_update_schema_rejects_unknown_resource_field():
    with pytest.raises(ValidationError):
        ResourceInventoryUpdate.model_validate({"resource_type": "FOOD"})


def test_inventory_model_defaults_to_unknown_status(valid_inventory_model_data):
    data = deepcopy(valid_inventory_model_data)
    del data["status"]

    inventory = ResourceInventory.model_validate(data)
    assert inventory.status == InventoryStatus.UNKNOWN


def test_inventory_model_defaults_to_unconfirmed_availability(
    valid_inventory_model_data,
):
    data = deepcopy(valid_inventory_model_data)
    del data["availability_confirmed"]

    inventory = ResourceInventory.model_validate(data)
    assert inventory.availability_confirmed is False
