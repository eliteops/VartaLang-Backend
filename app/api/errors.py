"""Generic API error envelope (PRD FR-11: never expose upstream details)."""

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

INVALID_MSG = "Please check your inputs and try again."
LIMIT_MSG = "Too many searches right now. Please try again later."
DOWN_MSG = "Search is unavailable right now. Please try again later."


def error_payload(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(status_code=422, content=error_payload("invalid_input", INVALID_MSG))


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content=error_payload("rate_limited", LIMIT_MSG))


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return JSONResponse(status_code=404, content=error_payload("not_found", "Not found."))
    message = str(exc.detail) if isinstance(exc.detail, str) else "Request failed."
    return JSONResponse(
        status_code=exc.status_code, content=error_payload("request_failed", message)
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content=error_payload("internal_error", DOWN_MSG))
