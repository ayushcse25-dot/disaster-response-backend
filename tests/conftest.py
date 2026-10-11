import os

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.api.auth_deps import get_current_user
from app.core.config import get_settings
from app.models.user import Principal, Role
from app.main import app

# Tests never talk to a real cluster: a dummy URI satisfies Settings and overrides any .env value.
os.environ["MONGODB_URI"] = "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=100"


class FakeDatabase:
    """Stands in for AsyncDatabase so tests need no MongoDB, credentials or network."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.ping_calls = 0

    async def command(self, name: str) -> dict:
        assert name == "ping"
        self.ping_calls += 1
        if self._error is not None:
            raise self._error
        return {"ok": 1.0}


TEST_AUTHORITY = Principal(user_id="test-authority", role=Role.AUTHORITY, display_name="Test authority")


@pytest.fixture(autouse=True)
def _reset_state():
    get_settings.cache_clear()
    app.dependency_overrides.clear()
    # API tests act as an authority unless they replace or remove this override.
    app.dependency_overrides[get_current_user] = lambda: TEST_AUTHORITY
    yield
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    # Not used as a context manager, so the lifespan (and MongoDB) is not started.
    return TestClient(app)


# Integration tests use a throwaway database on a local replica set and are
# skipped when none is reachable (override with TEST_MONGODB_URI).
TEST_MONGODB_URI = os.environ.get(
    "TEST_MONGODB_URI",
    "mongodb://localhost:27017/?replicaSet=rs0&serverSelectionTimeoutMS=500",
)


@pytest_asyncio.fixture
async def live_db():
    from uuid import uuid4

    from pymongo import AsyncMongoClient

    from app.db.indexes import ensure_indexes

    client = AsyncMongoClient(TEST_MONGODB_URI)
    try:
        await client.admin.command("ping")
    except Exception:
        await client.close()
        pytest.skip("No local MongoDB replica set for integration tests.")
    name = f"drp_test_{uuid4().hex[:10]}"
    database = client[name]
    await ensure_indexes(database)
    try:
        yield database
    finally:
        await client.drop_database(name)
        await client.close()


@pytest_asyncio.fixture
async def seeded_db(live_db):
    """live_db with the sample seed loaded (timestamps relative to now)."""
    from scripts.seed_sample import seed

    await seed(live_db)
    return live_db
