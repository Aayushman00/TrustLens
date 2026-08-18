"""Structured API errors — {code, message, details} (ADR 0007)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("trustlens.api")


class AppError(Exception):
    """Base application error with stable client-facing payload."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", *, details: dict[str, Any] | None = None) -> None:
        super().__init__("NOT_FOUND", message, status_code=404, details=details)


class ValidationAppError(AppError):
    def __init__(self, message: str = "Validation failed", *, details: dict[str, Any] | None = None) -> None:
        super().__init__("VALIDATION_ERROR", message, status_code=422, details=details)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict", *, details: dict[str, Any] | None = None) -> None:
        super().__init__("CONFLICT", message, status_code=409, details=details)


class UnauthorizedError(AppError):
    """Missing/invalid/expired token, or bad login credentials."""

    def __init__(
        self,
        message: str = "Unauthorized",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("UNAUTHORIZED", message, status_code=401, details=details)


class InvalidTokenError(AppError):
    """JWT decode/validation failure (bad signature, malformed, or expired)."""

    def __init__(
        self,
        message: str = "Invalid or expired token",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("INVALID_TOKEN", message, status_code=401, details=details)


class ForbiddenError(AppError):
    """Valid token but insufficient role/ownership for this action."""

    def __init__(
        self,
        message: str = "Forbidden",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("FORBIDDEN", message, status_code=403, details=details)


class NotImplementedAppError(AppError):
    """Stub endpoints return 501 until their target phase."""

    def __init__(
        self,
        message: str = "Not implemented",
        *,
        phase: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = dict(details or {})
        if phase is not None:
            payload.setdefault("phase", phase)
        super().__init__("NOT_IMPLEMENTED", message, status_code=501, details=payload)


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "details": details or {}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        logger.warning(
            "app_error code=%s status=%s request_id=%s message=%s",
            exc.code,
            exc.status_code,
            request_id,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details),
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            content = detail
        else:
            content = error_body("HTTP_ERROR", str(detail), {})
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        # exc.errors() may embed raw exception objects (e.g. ctx.error from a
        # model_validator's ValueError) that json.dumps can't serialize directly.
        errors = jsonable_encoder(exc.errors())
        return JSONResponse(
            status_code=422,
            content=error_body(
                "VALIDATION_ERROR",
                "Request validation failed",
                {"errors": errors},
            ),
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        logger.exception("unhandled_error request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            content=error_body("INTERNAL_ERROR", "An unexpected error occurred", {}),
            headers={"X-Request-ID": request_id},
        )
