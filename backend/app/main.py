"""TrustLens FastAPI entrypoint — Phase 4 backend skeleton."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.middleware import RequestIdMiddleware, configure_request_id_logging
from app.core.config import get_settings
from app.core.s3 import get_s3_client
from app.routers import health
from app.routers.v1 import api_router


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] request_id=%(request_id)s %(message)s",
    )
    configure_request_id_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.log_level)
    log = logging.getLogger("trustlens.api")
    log.info("trustlens-api starting (env=%s, phase=22)", settings.app_env)
    client = get_s3_client(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
    )
    if client is not None:
        log.info(
            "s3 client configured (endpoint=%s, bucket=%s)",
            settings.s3_endpoint,
            settings.s3_bucket,
        )
    else:
        log.info("s3 client not configured (skipped)")
    yield
    log.info("trustlens-api shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TrustLens API",
        version="0.20.1",
        description=(
            "Phase 22 — Opt-in leaderboard (ADR 0013): evaluations are private by "
            "default; POST /v1/evaluations/{id}/publish (owner/admin, FINALIZED "
            "only, idempotent) opts a result in and /unpublish revokes it — "
            "finalize never auto-publishes. GET /v1/leaderboard lists only "
            "published finals sorted by original FRIES score, with task/dataset/"
            "evaluation_mode filters, cursor pagination, report URIs, and a "
            "non-comparability note when no task filter is given (no universal "
            "cross-task trust ranking). Next: Phase 23 frontend demo UI; "
            "Phases 20-21 attack sim are post-MVP."
        ),
        lifespan=lifespan,
    )
    # Middleware order: last added runs first for requests.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router)
    return app


app = create_app()
