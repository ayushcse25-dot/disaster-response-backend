"""Shared query helper for separating real records from seeded sample data."""

from typing import Any


def with_sample_filter(query: dict[str, Any], include_sample: bool) -> dict[str, Any]:
    """Add is_sample != true to the query when sample records must be excluded."""
    if include_sample:
        return query
    return {**query, "is_sample": {"$ne": True}}
