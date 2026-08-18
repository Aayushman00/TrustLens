"""Request-ID middleware and logging helpers."""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger("trustlens.api.access")


class RequestIdFilter(logging.Filter):
    """Inject request_id from contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("-")
        return True


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generate/propagate X-Request-ID and log per-request access lines."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("X-Request-ID")
        request_id = incoming.strip() if incoming and incoming.strip() else str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
                request.method,
                request.url.path,
                500,
                duration_ms,
                request_id,
            )
            raise
        else:
            duration_ms = (time.perf_counter() - started) * 1000
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                request_id,
            )
            return response
        finally:
            request_id_ctx.reset(token)


def configure_request_id_logging() -> None:
    """Attach RequestIdFilter to root / trustlens loggers (idempotent)."""
    root = logging.getLogger()
    filt = RequestIdFilter()
    if not any(isinstance(f, RequestIdFilter) for f in root.filters):
        root.addFilter(filt)
    for name in ("trustlens.api", "trustlens.api.access"):
        log = logging.getLogger(name)
        if not any(isinstance(f, RequestIdFilter) for f in log.filters):
            log.addFilter(filt)
