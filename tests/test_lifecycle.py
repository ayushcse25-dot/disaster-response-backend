"""The MongoDB client is created once at startup, reused, and closed at shutdown."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.mongo import create_mongo_client
from app.main import app
from tests.conftest import FakeDatabase


class FakeClient:
    def __init__(self) -> None:
        self.database = FakeDatabase()
        self.requested_db_name: str | None = None
        self.close_calls = 0

    def __getitem__(self, name: str) -> FakeDatabase:
        self.requested_db_name = name
        return self.database

    async def close(self) -> None:
        self.close_calls += 1


def test_client_created_once_reused_and_closed(monkeypatch) -> None:
    monkeypatch.setenv("MONGODB_URI", "mongodb://placeholder.invalid:27017")
    monkeypatch.setenv("MONGODB_DB_NAME", "test_db")
    created: list[FakeClient] = []

    def fake_create(settings: Settings) -> FakeClient:
        created.append(FakeClient())
        return created[0]

    monkeypatch.setattr("app.main.create_mongo_client", fake_create)

    with TestClient(app) as running:
        first = running.get("/health/ready")
        second = running.get("/health/ready")
        assert created[0].close_calls == 0  # still open while serving

    assert first.status_code == 200 and second.status_code == 200
    assert len(created) == 1  # no per-request client
    assert created[0].requested_db_name == "test_db"
    assert created[0].database.ping_calls == 2  # every readiness call really pinged
    assert created[0].close_calls == 1  # closed on shutdown


def test_invalid_uri_fails_startup_without_leaking_it() -> None:
    # Passes the scheme check but is rejected by the driver (unescaped '@' in the password).
    settings = Settings(_env_file=None, mongodb_uri="mongodb://user:pa@ss-word@host:27017/")

    with pytest.raises(RuntimeError) as excinfo:
        create_mongo_client(settings)

    assert "pa@ss-word" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True
