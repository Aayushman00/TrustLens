"""Worker settings — Phase 2 Redis / S3 connectivity (no Celery tasks yet)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_WORKER_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _WORKER_ROOT.parent


def _settings_env_files() -> tuple[str, ...]:
    candidates = (
        _REPO_ROOT / ".env",
        _WORKER_ROOT / ".env",
        Path.cwd() / ".env",
    )
    return tuple(str(path) for path in candidates if path.is_file())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_settings_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str | None = None
    redis_url: str | None = None

    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "trustlens"
    s3_region: str = "us-east-1"

    worker_heartbeat_seconds: int = 30
    hf_token: str | None = None
    # Read by app.osd.hybrid.HybridOSDAgent (vendored verbatim from backend/app/osd
    # via Dockerfile.worker) — must be kept in sync with backend/app/core/config.py's
    # field of the same name.
    gemini_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
