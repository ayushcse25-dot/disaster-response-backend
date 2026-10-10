"""Application settings, loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration. Environment variable names match field names (case-insensitive)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Validation errors must never echo the rejected value: for MONGODB_URI
        # that value contains the database password.
        hide_input_in_errors=True,
    )

    environment: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Required: there is deliberately no default, so credentials never live in code.
    mongodb_uri: SecretStr
    mongodb_db_name: str = Field(default="disaster_response", min_length=1)
    mongodb_server_selection_timeout_ms: int = Field(default=5000, ge=100)

    @field_validator("mongodb_uri")
    @classmethod
    def _check_mongodb_uri(cls, value: SecretStr) -> SecretStr:
        uri = value.get_secret_value().strip()
        if not uri.startswith(("mongodb://", "mongodb+srv://")):
            # Do not include the value in the message.
            raise ValueError("MONGODB_URI must start with 'mongodb://' or 'mongodb+srv://'")
        return SecretStr(uri)


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()  # type: ignore[call-arg]  # mongodb_uri is supplied by the environment
