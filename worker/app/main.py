"""TrustLens worker entrypoint — Phase 1 shell (no queue tasks)."""

from __future__ import annotations

import logging
import signal
import sys
import time

from app.core.config import get_settings

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
    log.info("trustlens-worker ready (phase 1 shell)")

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    # Idle until interrupt so `python -m app.main` stays up like a process shell.
    while not _shutdown:
        time.sleep(0.5)

    log.info("trustlens-worker exited cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
