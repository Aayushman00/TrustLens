"""TrustLens FastAPI entrypoint — Phase 4 backend skeleton."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.middleware import RequestIdMiddleware, configure_request_id_logging
from app.core.config import get_settings
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
    log.info("artifact storage_dir=%s", settings.storage_dir or "unset (storage disabled)")
    yield
    log.info("trustlens-api shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TrustLens API",
        version="0.20.1",
        description=(
            "TrustLens v1 API — local-first ML evaluation. Default assessment "
            "engine is deterministic: probes emit evidence; O/S/D are not generated "
            "without a validated mapping; FRIES is withheld unless complete O/S/D "
            "exist (legacy_heuristic is admin-only). Evaluation modes AI_AUTONOMOUS "
            "and AI_ASSISTED are human-review workflow flags, not LLM interpretation."
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
