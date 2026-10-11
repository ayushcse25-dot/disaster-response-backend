"""MongoDB repository for the source registry."""

from typing import Any

from app.models.source import SourceRegistryEntry


class SourceRepository:
    """Read source registry entries from MongoDB."""

    COLLECTION_NAME = "sources"

    def __init__(self, database: Any) -> None:
        self.collection = database[self.COLLECTION_NAME]

    async def get_many(self, source_ids: list[str]) -> dict[str, SourceRegistryEntry]:
        """Return the registry entries that exist for the given IDs."""

        if not source_ids:
            return {}

        cursor = self.collection.find({"_id": {"$in": list(set(source_ids))}})
        sources: dict[str, SourceRegistryEntry] = {}

        for document in await cursor.to_list(length=None):
            document["source_id"] = document.pop("_id")
            entry = SourceRegistryEntry.model_validate(document)
            sources[entry.source_id] = entry

        return sources
