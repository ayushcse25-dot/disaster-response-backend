"""Login, account lookup and NGO worker management."""

import secrets
from typing import Any
from uuid import uuid4

from app.core.security import hash_password, verify_password
from app.models.user import AccountStatus, Principal, Role, UserAccount

USERS = "users"


class AuthError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _principal(document: dict[str, Any]) -> Principal:
    return Principal(
        user_id=document["_id"], role=document["role"], display_name=document["display_name"],
        ngo_id=document.get("ngo_id"), worker_id=document.get("worker_id"),
    )


def _check(document: dict[str, Any] | None, password: str) -> Principal:
    # The same message for unknown account and wrong password.
    if document is None or not verify_password(password, document.get("password_hash", "")):
        raise AuthError("INVALID_CREDENTIALS", "Invalid credentials.")
    if document.get("status") != AccountStatus.ACTIVE.value:
        raise AuthError("ACCOUNT_DISABLED", "This account is disabled.")
    return _principal(document)


async def authenticate_staff(database: Any, email: str, password: str) -> Principal:
    document = await database[USERS].find_one(
        {"email": email.strip().casefold(), "role": {"$in": [Role.AUTHORITY.value, Role.NGO_ADMIN.value]}}
    )
    return _check(document, password)


async def authenticate_worker(database: Any, ngo_code: str, worker_id: str, password: str) -> Principal:
    organisation = await database["organisations"].find_one({"ngo_code": ngo_code.strip().upper()})
    document = None
    if organisation is not None:
        document = await database[USERS].find_one({
            "ngo_id": organisation["_id"], "worker_id": worker_id.strip().upper(),
            "role": Role.WORKER.value,
        })
    return _check(document, password)


async def load_active_principal(database: Any, user_id: str) -> Principal:
    document = await database[USERS].find_one({"_id": user_id})
    if document is None:
        raise AuthError("UNAUTHENTICATED", "Account not found.")
    if document.get("status") != AccountStatus.ACTIVE.value:
        raise AuthError("ACCOUNT_DISABLED", "This account is disabled.")
    return _principal(document)


async def insert_account(database: Any, account: UserAccount) -> None:
    document = account.model_dump(mode="json")
    document["_id"] = document.pop("user_id")
    await database[USERS].insert_one(document)


async def create_worker(
    database: Any, ngo_id: str, display_name: str, *, is_sample: bool = False,
    worker_id: str | None = None,
) -> tuple[Principal, str]:
    """Create a worker. Returns the principal and a temporary password shown only once."""
    temporary_password = secrets.token_urlsafe(9)
    account = UserAccount(
        user_id=str(uuid4()), role=Role.WORKER, display_name=display_name, ngo_id=ngo_id,
        worker_id=worker_id or f"W-{secrets.token_hex(3).upper()}",
        password_hash=hash_password(temporary_password), must_change_password=True,
        is_sample=is_sample,
    )
    await insert_account(database, account)
    return Principal(user_id=account.user_id, role=account.role, display_name=display_name,
                     ngo_id=ngo_id, worker_id=account.worker_id), temporary_password


async def list_workers(database: Any, ngo_id: str) -> list[dict[str, Any]]:
    documents = await database[USERS].find(
        {"ngo_id": ngo_id, "role": Role.WORKER.value},
        {"_id": 1, "worker_id": 1, "display_name": 1, "status": 1},
    ).sort("worker_id", 1).to_list(length=1000)
    return [{"user_id": d["_id"], "worker_id": d["worker_id"], "display_name": d["display_name"],
             "status": d["status"]} for d in documents]


async def set_worker_status(database: Any, ngo_id: str, worker_id: str, status: AccountStatus) -> bool:
    result = await database[USERS].update_one(
        {"ngo_id": ngo_id, "worker_id": worker_id, "role": Role.WORKER.value},
        {"$set": {"status": status.value}},
    )
    return result.matched_count == 1
