"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent


def _settings_env_files() -> tuple[str, ...]:
    """Load repo-root ``.env`` first so native runs work from ``backend/``."""
    candidates = (
        _REPO_ROOT / ".env",
        _BACKEND_ROOT / ".env",
        Path.cwd() / ".env",
    )
    return tuple(str(path) for path in candidates if path.is_file())


class Settings(BaseSettings):
    """Application settings — DB / Redis / S3 config."""

    model_config = SettingsConfigDict(
        env_file=_settings_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"

    # Sync SQLAlchemy URL (postgresql+psycopg2://...). Optional for unit tests.
    database_url: str | None = None
    redis_url: str | None = None

    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "trustlens"
    s3_region: str = "us-east-1"

    hf_token: str | None = None

    # Celery producer (Phase 7). When true, tasks run inline (tests).
    celery_task_always_eager: bool = False

    # Phase 19: PDF projection of the canonical JSON report. Disable when
    # WeasyPrint OS libs (Pango/HarfBuzz) are unavailable — reports then ship
    # JSON+HTML only with pdf_uri=null.
    report_pdf_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
