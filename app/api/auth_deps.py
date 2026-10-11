"""Authentication and authorisation dependencies.

Every route except /health depends on get_current_user (through require_roles).
The account is re-read on each request, so disabling it takes effect immediately.
"""

from typing import Annotated, Any

from fastapi import Depends, Request

from app.api.deps import get_database
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import decode_token
from app.models.user import Principal, Role
from app.services.auth_service import AuthError, load_active_principal

STAFF = (Role.AUTHORITY, Role.NGO_ADMIN)


async def get_current_user(request: Request) -> Principal:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(401, "UNAUTHENTICATED", "A bearer token is required.",
                       headers={"WWW-Authenticate": "Bearer"})
    claims = decode_token(token, get_settings().auth_secret.get_secret_value())
    if claims is None or not isinstance(claims.get("sub"), str):
        raise ApiError(401, "INVALID_TOKEN", "The token is invalid or expired.",
                       headers={"WWW-Authenticate": "Bearer"})
    try:
        return await load_active_principal(get_database(request), claims["sub"])
    except AuthError as exc:
        raise ApiError(401, exc.code, exc.detail) from exc


CurrentUser = Annotated[Principal, Depends(get_current_user)]


def require_roles(*roles: Role) -> Any:
    async def dependency(user: CurrentUser) -> Principal:
        if user.role not in roles:
            raise ApiError(403, "FORBIDDEN_ROLE", f"Role {user.role} cannot use this endpoint.")
        return user

    return dependency


def ensure_ngo_scope(user: Principal, ngo_id: str | None) -> None:
    """AUTHORITY sees everything; NGO roles only their own organisation's records."""
    if user.role != Role.AUTHORITY and (ngo_id is None or user.ngo_id != ngo_id):
        raise ApiError(403, "NGO_SCOPE", "This record belongs to another organisation.")
