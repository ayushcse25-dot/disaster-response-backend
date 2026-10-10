"""MongoDB persistence for allocation plans."""

from typing import Any
from pymongo.errors import DuplicateKeyError
from app.models.allocation_plan import AllocationPlanRecord


class AllocationPlanRepository:
    COLLECTION_NAME = "allocation_plans"

    def __init__(self, database: Any) -> None:
        self.collection = database[self.COLLECTION_NAME]

    async def create(self, record: AllocationPlanRecord) -> AllocationPlanRecord:
        document = record.model_dump(mode="json")
        document["_id"] = document.pop("plan_id")
        try:
            await self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise ValueError("Allocation plan ID already exists.") from exc
        return record

    async def get_by_id(self, plan_id: str) -> AllocationPlanRecord | None:
        document = await self.collection.find_one({"_id": plan_id})
        if document is None:
            return None
        document["plan_id"] = document.pop("_id")
        return AllocationPlanRecord.model_validate(document)

    async def list_by_event(
        self, event_id: str, *, limit: int = 20, skip: int = 0
    ) -> list[AllocationPlanRecord]:
        if not event_id or not event_id.strip():
            raise ValueError("Event ID cannot be empty.")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        if skip < 0:
            raise ValueError("skip cannot be negative.")

        cursor = (
            self.collection.find({"event_id": event_id})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        documents = await cursor.to_list(length=limit)
        records = []
        for document in documents:
            document["plan_id"] = document.pop("_id")
            records.append(AllocationPlanRecord.model_validate(document))
        return records
