"""GET /health — dependency connectivity checks."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request, Response

from app.core.config import get_settings
from app.core.db import check_postgres
from app.core.redis_client import check_redis
from app.core.s3 import check_s3

router = APIRouter(tags=["health"])
logger = logging.getLogger("trustlens.api")


def run_health_checks() -> dict[str, Any]:
    """Build health payload. Critical deps: postgres + redis when configured."""
    settings = get_settings()
    checks = {
        "postgres": check_postgres(settings.database_url),
        "redis": check_redis(settings.redis_url),
        "minio": check_s3(
            endpoint=settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            bucket=settings.s3_bucket,
            region=settings.s3_region,
        ),
    }

    critical_failed = any(checks[name] == "error" for name in ("postgres", "redis"))
    status = "error" if critical_failed else "ok"
    return {
        "status": status,
        "service": "trustlens-api",
        "checks": checks,
    }


@router.get("/health")
def health(request: Request, response: Response) -> dict[str, Any]:
    payload = run_health_checks()
    if payload["status"] != "ok":
        response.status_code = 503
        request_id = getattr(request.state, "request_id", "-")
        logger.warning(
            "health_check_failed request_id=%s checks=%s",
            request_id,
            payload["checks"],
        )
    return payload
