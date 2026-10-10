from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Same shape for every health endpoint.

    status: "ok" when every listed check is up, otherwise "unavailable".
    checks: one entry per component that this endpoint verified.
    """

    status: Literal["ok", "unavailable"]
    checks: dict[str, Literal["up", "down"]]
