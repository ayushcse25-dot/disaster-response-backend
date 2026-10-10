"""Shared FastAPI dependencies."""

from fastapi import Request
from pymongo.asynchronous.database import AsyncDatabase


def get_database(request: Request) -> AsyncDatabase:
    """Return the database handle created during application startup."""
    return request.app.state.mongo_db
