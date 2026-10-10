"""Application-wide error handlers."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)


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
        content={"detail": "Database temporarily unavailable."},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PyMongoError, handle_database_error)
