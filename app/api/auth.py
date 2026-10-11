"""Login, current-user and NGO worker management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.api.auth_deps import CurrentUser, ensure_ngo_scope, require_roles
from app.api.deps import get_database
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import create_token
from app.models.user import AccountStatus, Principal, Role
from app.services import auth_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/api/v1", tags=["Auth"])
Database = Annotated[AsyncDatabase, Depends(get_database)]


class StaffLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class WorkerLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ngo_code: str = Field(min_length=2, max_length=30)
    worker_id: str = Field(min_length=1, max_length=30)
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Principal


class WorkerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=200)


class WorkerCreated(BaseModel):
    worker: Principal
    temporary_password: str = Field(description="Shown once; it is stored only as a hash.")


def _token(user: Principal) -> TokenResponse:
    settings = get_settings()
    ttl = settings.token_ttl_minutes * 60
    token = create_token(
        {"sub": user.user_id, "role": user.role.value, "ngo_id": user.ngo_id},
        settings.auth_secret.get_secret_value(), ttl,
    )
    return TokenResponse(access_token=token, expires_in=ttl, user=user)


def _auth_error(exc: AuthError) -> ApiError:
    return ApiError(401, exc.code, exc.detail)


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: StaffLogin, database: Database) -> TokenResponse:
    """Authority and NGO staff log in with email and password."""
    try:
        return _token(await auth_service.authenticate_staff(database, body.email, body.password))
    except AuthError as exc:
        raise _auth_error(exc) from exc


@router.post("/auth/worker-login", response_model=TokenResponse)
async def worker_login(body: WorkerLogin, database: Database) -> TokenResponse:
    """Field workers log in with their NGO code, worker ID and password."""
    try:
        return _token(await auth_service.authenticate_worker(
            database, body.ngo_code, body.worker_id, body.password
        ))
    except AuthError as exc:
        raise _auth_error(exc) from exc


@router.get("/me", response_model=Principal)
async def me(user: CurrentUser) -> Principal:
    return user


NgoAdmin = Annotated[Principal, Depends(require_roles(Role.NGO_ADMIN, Role.AUTHORITY))]


@router.post("/ngos/{ngo_id}/workers", response_model=WorkerCreated,
             status_code=status.HTTP_201_CREATED)
async def create_worker(ngo_id: str, body: WorkerCreate, user: NgoAdmin,
                        database: Database) -> WorkerCreated:
    """Issue a worker ID and temporary password. The password is returned only here."""
    ensure_ngo_scope(user, ngo_id)
    if await database["organisations"].find_one({"_id": ngo_id}, {"_id": 1}) is None:
        raise ApiError(404, "NGO_NOT_FOUND", "Organisation not found.")
    worker, password = await auth_service.create_worker(database, ngo_id, body.display_name)
    return WorkerCreated(worker=worker, temporary_password=password)


@router.get("/ngos/{ngo_id}/workers")
async def list_workers(ngo_id: str, user: NgoAdmin, database: Database) -> list[dict]:
    ensure_ngo_scope(user, ngo_id)
    return await auth_service.list_workers(database, ngo_id)


@router.post("/ngos/{ngo_id}/workers/{worker_id}/disable")
async def disable_worker(ngo_id: str, worker_id: str, user: NgoAdmin,
                         database: Database) -> dict:
    ensure_ngo_scope(user, ngo_id)
    if not await auth_service.set_worker_status(database, ngo_id, worker_id, AccountStatus.DISABLED):
        raise ApiError(404, "WORKER_NOT_FOUND", "Worker not found.")
    return {"worker_id": worker_id, "status": AccountStatus.DISABLED}
