from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.enums import (
    EventVerificationStatus,
    ObservationType,
    SourceApprovalStatus,
    SourceCategory,
)
from app.models.field_report import FieldReport, FieldReportType
from app.models.flood_event import GeoLocation
from app.models.flood_observation import FloodObservation
from app.models.resource_inventory import (
    InventoryStatus,
    ResourceInventory,
    ResourceType,
)
from app.models.resource_need import NeedType, ResourceNeed
from app.models.source import SourceRegistryEntry


NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
NAIVE_NOW = datetime(2026, 10, 9, 12, 0)


def make_inventory(**overrides):
    data = {
        "inventory_id": "inventory-test-001",
        "organisation_id": "organisation-test-001",
        "resource_type": ResourceType.DRINKING_WATER,
        "resource_name": "Drinking water",
        "quantity_total": 100,
        "quantity_reserved": 20,
        "quantity_deployed": 30,
        "quantity_unit": "litres",
        "storage_location": "Test warehouse",
        "status": InventoryStatus.AVAILABLE,
        "availability_confirmed": True,
        "last_verified_at": NOW,
    }
    data.update(overrides)
    return ResourceInventory(**data)


def make_observation(**overrides):
    data = {
        "observation_id": "observation-test-001",
        "source_id": "source-test-001",
        "observation_type": ObservationType.NEWS_REPORT,
        "title": "Flooding reported",
        "description": "Flooding reported in the test location.",
        "location_name": "Patna",
        "state": "Bihar",
        "observed_at": NOW,
    }
    data.update(overrides)
    return FloodObservation(**data)


def make_field_report(**overrides):
    data = {
        "report_id": "report-test-001",
        "event_id": "event-test-001",
        "team_id": "team-test-001",
        "report_type": FieldReportType.ROAD_BLOCKED,
        "title": "Road blocked",
        "description": "Floodwater has blocked the road.",
        "location_name": "Patna",
        "observed_at": NOW,
    }
    data.update(overrides)
    return FieldReport(**data)


def make_source(**overrides):
    data = {
        "source_id": "source-test-001",
        "name": "Test monitoring source",
        "category": SourceCategory.MANUAL,
        "access_method": "MANUAL_ENTRY",
    }
    data.update(overrides)
    return SourceRegistryEntry(**data)


def test_inventory_rejects_reserved_and_deployed_quantities_above_total():
    with pytest.raises(ValidationError):
        make_inventory(quantity_reserved=80, quantity_deployed=40)


def test_inventory_accepts_valid_allocated_quantities():
    inventory = make_inventory()
    available_quantity = (
        inventory.quantity_total
        - inventory.quantity_reserved
        - inventory.quantity_deployed
    )
    assert available_quantity == 50


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity_total", -1),
        ("quantity_reserved", -1),
        ("quantity_deployed", -1),
    ],
)
def test_inventory_rejects_negative_quantities(field, value):
    with pytest.raises(ValidationError):
        make_inventory(**{field: value})


def test_inventory_rejects_naive_last_verified_at():
    with pytest.raises(ValidationError, match="timezone"):
        make_inventory(last_verified_at=NAIVE_NOW)


def test_inventory_accepts_missing_last_verified_at():
    inventory = make_inventory(last_verified_at=None)
    assert inventory.last_verified_at is None


def test_inventory_rejects_invalid_resource_type():
    with pytest.raises(ValidationError):
        make_inventory(resource_type="WATER")


def test_inventory_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        make_inventory(unexpected_field="not allowed")


def test_resource_need_rejects_fulfilled_quantity_above_requested():
    with pytest.raises(ValidationError):
        ResourceNeed(
            need_id="need-test-001",
            event_id="event-test-001",
            location_id="location-test-001",
            need_type=NeedType.DRINKING_WATER,
            description="Drinking water required",
            quantity_requested=100,
            quantity_unit="litres",
            quantity_fulfilled=120,
        )


def test_flood_observation_rejects_naive_observed_at():
    with pytest.raises(ValidationError, match="timezone"):
        make_observation(observed_at=NAIVE_NOW)


def test_flood_observation_rejects_naive_received_at():
    with pytest.raises(ValidationError, match="timezone"):
        make_observation(received_at=NAIVE_NOW)


def test_flood_observation_accepts_timezone_aware_timestamps():
    observation = make_observation(
        observed_at=NOW,
        received_at=NOW,
    )
    assert observation.observed_at == NOW
    assert observation.received_at == NOW


def test_flood_observation_defaults_to_unverified():
    observation = make_observation()
    assert (
        observation.verification_status
        == EventVerificationStatus.UNVERIFIED
    )


def test_flood_observation_rejects_invalid_source_url():
    with pytest.raises(ValidationError):
        make_observation(source_url="not-a-valid-url")


def test_flood_observation_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        make_observation(unexpected_field="not allowed")


def test_field_report_rejects_naive_observed_at():
    with pytest.raises(ValidationError, match="timezone"):
        make_field_report(observed_at=NAIVE_NOW)


def test_field_report_rejects_naive_received_at():
    with pytest.raises(ValidationError, match="timezone"):
        make_field_report(received_at=NAIVE_NOW)


def test_field_report_defaults_to_received_status():
    report = make_field_report()
    assert report.status.value == "RECEIVED"
    assert report.requires_reassessment is True


def test_field_report_accepts_valid_coordinates():
    report = make_field_report(
        coordinates=GeoLocation(latitude=25.5941, longitude=85.1376)
    )
    assert report.coordinates is not None
    assert report.coordinates.latitude == 25.5941


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (91, 0),
        (-91, 0),
        (0, 181),
        (0, -181),
    ],
)
def test_geolocation_rejects_coordinates_out_of_range(latitude, longitude):
    with pytest.raises(ValidationError):
        GeoLocation(latitude=latitude, longitude=longitude)


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (-90, -180),
        (90, 180),
        (0, 0),
    ],
)
def test_geolocation_accepts_coordinate_boundaries(latitude, longitude):
    location = GeoLocation(latitude=latitude, longitude=longitude)
    assert location.latitude == latitude
    assert location.longitude == longitude


def test_field_report_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        make_field_report(unexpected_field="not allowed")


def test_source_defaults_to_candidate_approval():
    source = make_source()
    assert source.approval_status == SourceApprovalStatus.CANDIDATE


def test_source_defaults_description_to_empty_string():
    source = make_source()
    assert source.description == ""


def test_source_accepts_valid_website_url():
    source = make_source(website_url="https://example.com")
    assert str(source.website_url) == "https://example.com/"


def test_source_rejects_invalid_website_url():
    with pytest.raises(ValidationError):
        make_source(website_url="not-a-valid-url")


def test_source_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        make_source(unexpected_field="not allowed")


def test_source_rejects_invalid_category():
    with pytest.raises(ValidationError):
        make_source(category="UNKNOWN_CATEGORY")


def test_source_has_timezone_aware_default_timestamps():
    source = make_source()
    assert source.created_at.tzinfo is not None
    assert source.updated_at.tzinfo is not None
