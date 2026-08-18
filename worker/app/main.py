"""TrustLens worker entrypoint — deprecated heartbeat loop (Phase 2).

Docker Compose and ``make dev-worker`` now run Celery::

    celery -A app.celery_app worker --loglevel=INFO -Q trustlens

This module remains for native smoke tests that exercise Redis connectivity
without a broker consumer.
"""

from __future__ import annotations

import logging
import signal
import sys
import time

from app.core.config import get_settings
from app.core.redis_client import check_redis

_shutdown = False


def _handle_signal(signum: int, frame: object | None) -> None:
    global _shutdown
    _shutdown = True
    logging.getLogger("trustlens.worker").info(
        "received signal %s — shutting down",
        signum,
    )


def main() -> int:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    log = logging.getLogger("trustlens.worker")
    log.info(
        "trustlens-worker heartbeat shell (env=%s) — prefer celery worker in Phase 7+",
        settings.app_env,
    )
    log.info(
        "config: redis=%s s3_endpoint=%s bucket=%s heartbeat=%ss",
        "set" if settings.redis_url else "unset",
        settings.s3_endpoint or "unset",
        settings.s3_bucket,
        settings.worker_heartbeat_seconds,
    )

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    interval = max(1, settings.worker_heartbeat_seconds)
    next_beat = 0.0

    while not _shutdown:
        now = time.monotonic()
        if now >= next_beat:
            redis_status = check_redis(settings.redis_url)
            log.info(
                "heartbeat alive redis=%s",
                redis_status,
            )
            next_beat = now + interval
        time.sleep(0.5)

    log.info("trustlens-worker exited cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
