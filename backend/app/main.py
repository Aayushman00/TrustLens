"""TrustLens FastAPI entrypoint — Phase 1 health shell only."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.log_level)
    logging.getLogger("trustlens.api").info(
        "trustlens-api starting (env=%s, phase=1 shell)",
        settings.app_env,
    )
    yield
    logging.getLogger("trustlens.api").info("trustlens-api shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TrustLens API",
        version="0.1.0",
        description="Phase 1 repository bootstrap — health endpoint only.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": "trustlens-api"}

    return app


app = create_app()
