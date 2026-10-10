import asyncio
import time

from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.api.deps import get_database
from app.main import app
from tests.conftest import FakeDatabase

SENSITIVE_MARKERS = ("secret-password", "internal-host", "mongodb://", "mongodb+srv://", "27017")


def test_live_reports_application_up(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"application": "up"}}


def test_live_does_not_depend_on_the_database(client: TestClient) -> None:
    broken = FakeDatabase(error=ServerSelectionTimeoutError("down"))
    app.dependency_overrides[get_database] = lambda: broken

    response = client.get("/health/live")

    assert response.status_code == 200
    assert broken.ping_calls == 0


def test_ready_when_database_reachable(client: TestClient) -> None:
    database = FakeDatabase()
    app.dependency_overrides[get_database] = lambda: database

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "up"}}
    assert database.ping_calls == 1  # readiness really pinged the database


def test_ready_when_database_unreachable(client: TestClient) -> None:
    error = ServerSelectionTimeoutError("user:secret-password@internal-host:27017 timed out")
    app.dependency_overrides[get_database] = lambda: FakeDatabase(error=error)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "checks": {"database": "down"}}


def test_ready_error_response_contains_no_sensitive_information(client: TestClient) -> None:
    error = ServerSelectionTimeoutError(
        "mongodb+srv://user:secret-password@internal-host:27017 timed out"
    )
    app.dependency_overrides[get_database] = lambda: FakeDatabase(error=error)

    response = client.get("/health/ready")

    assert response.status_code == 503
    for marker in SENSITIVE_MARKERS:
        assert marker not in response.text


def test_ready_is_bounded_when_the_database_hangs(client: TestClient, monkeypatch) -> None:
    class HangingDatabase:
        async def command(self, name: str) -> dict:
            await asyncio.sleep(30)
            return {"ok": 1.0}

    monkeypatch.setattr("app.db.mongo.PING_TIMEOUT_SECONDS", 0.05)
    app.dependency_overrides[get_database] = lambda: HangingDatabase()

    started = time.monotonic()
    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "checks": {"database": "down"}}
    assert time.monotonic() - started < 5
