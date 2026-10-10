import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_mongodb_uri_is_required(monkeypatch) -> None:
    monkeypatch.delenv("MONGODB_URI", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_rejects_non_mongodb_uri_without_echoing_it() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, mongodb_uri="http://user:topsecret@host")

    assert "topsecret" not in str(excinfo.value)


def test_valid_uri_is_accepted_and_hidden_from_repr() -> None:
    settings = Settings(_env_file=None, mongodb_uri="mongodb+srv://user:topsecret@cluster.example/")

    assert settings.mongodb_uri.get_secret_value().startswith("mongodb+srv://")
    assert "topsecret" not in repr(settings)
    assert "topsecret" not in str(settings)


def test_defaults(monkeypatch) -> None:
    for name in ("MONGODB_DB_NAME", "MONGODB_SERVER_SELECTION_TIMEOUT_MS", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None, mongodb_uri="mongodb://localhost:27017")

    assert settings.mongodb_db_name == "disaster_response"
    assert settings.mongodb_server_selection_timeout_ms == 5000
    assert settings.log_level == "INFO"
