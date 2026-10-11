"""The is_sample flag is exposed in responses but cannot be set through the API."""

from unittest.mock import AsyncMock

from app.api.flood_events import get_flood_event_service
from app.main import app
from app.models.affected_location import AffectedLocation
from app.models.flood_event import FloodEvent
from app.models.flood_observation import FloodObservation
from app.models.source import SourceRegistryEntry


def test_models_default_to_not_sample():
    assert FloodEvent(event_id="e1", title="Flood", location_name="Patna", state="Bihar").is_sample is False
    assert AffectedLocation(location_id="l1", event_id="e1", location_name="Patna", state="Bihar").is_sample is False
    assert FloodObservation.model_fields["is_sample"].default is False
    assert SourceRegistryEntry.model_fields["is_sample"].default is False


def test_create_flood_event_rejects_is_sample(client):
    service = AsyncMock()
    app.dependency_overrides[get_flood_event_service] = lambda: service

    response = client.post(
        "/api/v1/flood-events",
        json={"title": "Flood", "location_name": "Patna", "state": "Bihar", "is_sample": True},
    )

    assert response.status_code == 422
    service.create_event.assert_not_awaited()


def test_resource_and_plan_models_default_to_not_sample():
    from app.models.allocation_plan import AllocationPlanRecord
    from app.models.resource_inventory import ResourceInventory
    from app.models.resource_need import ResourceNeed
    from app.models.response_team import ResponseTeam

    for model in (AllocationPlanRecord, ResourceInventory, ResourceNeed, ResponseTeam):
        assert model.model_fields["is_sample"].default is False


def test_create_payloads_reject_is_sample():
    import pytest
    from pydantic import ValidationError

    from app.schemas.resource_inventory import ResourceInventoryCreate
    from app.schemas.resource_need import ResourceNeedCreate
    from app.schemas.response_team import ResponseTeamCreate

    payloads = [
        (ResourceInventoryCreate, {"organisation_id": "o", "resource_type": "FOOD", "resource_name": "Rice",
                                   "quantity_total": 1, "quantity_unit": "kg", "storage_location": "Depot"}),
        (ResourceNeedCreate, {"event_id": "e", "location_id": "l", "need_type": "FOOD", "description": "Food"}),
        (ResponseTeamCreate, {"organisation_id": "o", "team_name": "Team", "personnel_count": 1}),
    ]
    for schema, payload in payloads:
        schema.model_validate(payload)
        with pytest.raises(ValidationError):
            schema.model_validate({**payload, "is_sample": True})
