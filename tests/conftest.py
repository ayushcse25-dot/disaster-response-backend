import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
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


@pytest.fixture(autouse=True)
def _reset_state():
    get_settings.cache_clear()
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    # Not used as a context manager, so the lifespan (and MongoDB) is not started.
    return TestClient(app)
