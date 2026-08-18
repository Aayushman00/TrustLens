"""Minimal Redis connectivity helpers for worker heartbeat."""

from __future__ import annotations

import redis


def check_redis(redis_url: str | None) -> str:
    """Return 'ok', 'error', or 'skipped' (URL unset)."""
    if not redis_url:
        return "skipped"
    client: redis.Redis | None = None
    try:
        client = redis.Redis.from_url(
            redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        if client.ping():
            return "ok"
        return "error"
    except Exception:
        return "error"
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
