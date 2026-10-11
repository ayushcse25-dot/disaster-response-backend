"""Generate and persist explainable allocation proposals."""

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from app.models.allocation_plan import AllocationPlanRecord
from app.repositories.affected_location_repository import AffectedLocationRepository
from app.repositories.allocation_plan_repository import AllocationPlanRepository
from app.repositories.flood_event_repository import FloodEventRepository
from app.repositories.resource_inventory_repository import ResourceInventoryRepository
from app.repositories.resource_need_repository import ResourceNeedRepository
from app.repositories.response_team_repository import ResponseTeamRepository
from app.services.allocation_engine import generate_allocation_plan


def _planning_snapshot_digest(
    *,
    event: Any,
    locations: list[Any],
    needs: list[Any],
    inventory: list[Any],
    teams: list[Any],
) -> str:
    """Hash a canonical representation of every planning input.

    The digest identifies the input snapshot used to generate a proposal.
    It is not a database transaction ID or a concurrency lock.
    """
    def serialize(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value

    def canonical_items(values: list[Any]) -> list[Any]:
        serialized = [serialize(value) for value in values]
        return sorted(
            serialized,
            key=lambda value: json.dumps(
                value, sort_keys=True, separators=(",", ":")
            ),
        )

    snapshot = {
        "event": serialize(event),
        "locations": canonical_items(locations),
        "needs": canonical_items(needs),
        "inventory": canonical_items(inventory),
        "teams": canonical_items(teams),
    }
    canonical = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


class AllocationPlanService:
    def __init__(
        self,
        *,
        plan_repository: AllocationPlanRepository,
        event_repository: FloodEventRepository,
        location_repository: AffectedLocationRepository,
        need_repository: ResourceNeedRepository,
        inventory_repository: ResourceInventoryRepository,
        team_repository: ResponseTeamRepository,
    ) -> None:
        self.plan_repository = plan_repository
        self.event_repository = event_repository
        self.location_repository = location_repository
        self.need_repository = need_repository
        self.inventory_repository = inventory_repository
        self.team_repository = team_repository

    async def build_for_event(
        self,
        event_id: str,
        *,
        organisation_id: str | None = None,
        version: int = 1,
    ) -> tuple[AllocationPlanRecord, str]:
        """Run the engine on the current snapshot without persisting anything.

        With organisation_id, only that organisation's inventory and teams are
        considered. Returns the unsaved record and the snapshot digest.
        """
        if not event_id or not event_id.strip():
            raise ValueError("Event ID cannot be empty.")

        event = await self.event_repository.get_by_id(event_id)
        if event is None:
            raise LookupError(f"Flood event '{event_id}' does not exist.")

        # Each loader either returns a complete bounded snapshot or fails.
        locations = await self.location_repository.list_for_planning()
        needs = await self.need_repository.list_for_planning()
        inventory = await self.inventory_repository.list_for_planning()
        teams = await self.team_repository.list_for_planning()
        if organisation_id is not None:
            inventory = [i for i in inventory if i.organisation_id == organisation_id]
            teams = [t for t in teams if t.organisation_id == organisation_id]

        # The legacy field name is retained for API compatibility, but the
        # digest covers every input that can influence this planning result.
        inventory_version = _planning_snapshot_digest(
            event=event,
            locations=locations,
            needs=needs,
            inventory=inventory,
            teams=teams,
        )

        generated_at = datetime.now(timezone.utc)
        result = generate_allocation_plan(
            event=event,
            locations=locations,
            needs=needs,
            inventory=inventory,
            teams=teams,
            generated_at=generated_at,
            inventory_state_version=inventory_version,
        )
        record = AllocationPlanRecord(
            plan_id=str(uuid4()),
            event_id=event.event_id,
            plan=result,
            created_at=generated_at,
            version=version,
            ngo_id=organisation_id,
        )
        return record, inventory_version

    async def generate_for_event(self, event_id: str) -> AllocationPlanRecord:
        record, _ = await self.build_for_event(event_id)
        latest = await self.plan_repository.latest_version(record.event_id)
        record.version = latest + 1
        return await self.plan_repository.create(record)

    async def get_plan(self, plan_id: str) -> AllocationPlanRecord | None:
        if not plan_id or not plan_id.strip():
            raise ValueError("Plan ID cannot be empty.")
        return await self.plan_repository.get_by_id(plan_id)

    async def list_plans(
        self, event_id: str, *, limit: int = 20, skip: int = 0, include_sample: bool = True
    ) -> list[AllocationPlanRecord]:
        if not event_id or not event_id.strip():
            raise ValueError("Event ID cannot be empty.")
        if await self.event_repository.get_by_id(event_id) is None:
            raise LookupError(f"Flood event '{event_id}' does not exist.")
        return await self.plan_repository.list_by_event(
            event_id, limit=limit, skip=skip, include_sample=include_sample
        )
