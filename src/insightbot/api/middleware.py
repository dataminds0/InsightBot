"""Middleware for request tracking and standardized error responses."""

import logging
import uuid
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware ensuring every HTTP request has an X-Request-ID.
    Propagates client-supplied X-Request-ID or generates a fresh UUID.
    Attaches the request ID to request.state and the HTTP response header.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_id = request.headers.get("X-Request-ID")
        request_id = (
            incoming_id.strip() if incoming_id and incoming_id.strip() else str(uuid.uuid4())
        )
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def _get_request_id(request: Request) -> str:
    """Safely obtain request ID from request state or fallback to a new UUID."""
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def setup_exception_handlers(app: FastAPI) -> None:
    """Register application-wide exception handlers with structured error envelopes."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        req_id = _get_request_id(request)
        try:
            status_phrase = HTTPStatus(exc.status_code).name
        except ValueError:
            status_phrase = "HTTP_ERROR"

        headers = dict(exc.headers or {})
        headers["X-Request-ID"] = req_id

        content: dict[str, Any] = {
            "detail": exc.detail,
            "error": {
                "code": status_phrase,
                "message": str(exc.detail),
                "request_id": req_id,
            },
        }
        return JSONResponse(status_code=exc.status_code, content=content, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        req_id = _get_request_id(request)
        headers = {"X-Request-ID": req_id}
        content: dict[str, Any] = {
            "detail": exc.errors(),
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "request_id": req_id,
                "details": exc.errors(),
            },
        }
        return JSONResponse(status_code=422, content=content, headers=headers)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = _get_request_id(request)
        logger.exception("Unhandled server exception for request %s: %s", req_id, exc)
        headers = {"X-Request-ID": req_id}
        content: dict[str, Any] = {
            "detail": "Internal server error.",
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error.",
                "request_id": req_id,
            },
        }
        return JSONResponse(status_code=500, content=content, headers=headers)
