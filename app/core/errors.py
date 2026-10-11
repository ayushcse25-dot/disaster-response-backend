"""Application-wide error handlers.

Every error body has a human-readable "detail" and a stable machine-readable "code".
"""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

DEFAULT_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


class ApiError(HTTPException):
    """An HTTPException carrying a stable error code."""

    def __init__(
        self, status_code: int, code: str, detail: Any, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = getattr(exc, "code", None) or DEFAULT_CODES.get(exc.status_code, "ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": jsonable_encoder(exc.detail), "code": code},
        headers=getattr(exc, "headers", None),
    )


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors()), "code": "VALIDATION_ERROR"},
    )


async def handle_database_error(request: Request, exc: Exception) -> JSONResponse:
    """Turn any PyMongo error into a generic 503.

    Only the exception type is logged and nothing from the driver is returned:
    its messages can contain hostnames or other connection details.
    """
    logger.error(
        "Database error on %s %s: %s", request.method, request.url.path, type(exc).__name__
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database temporarily unavailable.", "code": "DATABASE_UNAVAILABLE"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(PyMongoError, handle_database_error)
