"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

JWT_SECRET_PLACEHOLDER = "change-me-phase5-placeholder"


class Settings(BaseSettings):
    """Phase 5 settings — DB / Redis / S3 / JWT auth config."""

    model_config = SettingsConfigDict(
        env_file=".env",
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

    jwt_secret: str = JWT_SECRET_PLACEHOLDER
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7

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

    @model_validator(mode="after")
    def _check_jwt_secret_not_placeholder(self) -> "Settings":
        """Fail fast outside development/test if JWT_SECRET was never set."""
        if (
            self.app_env not in ("development", "test")
            and self.jwt_secret == JWT_SECRET_PLACEHOLDER
        ):
            raise ValueError(
                "JWT_SECRET must be set to a real secret when APP_ENV is not "
                "'development' or 'test'. Refusing to start with the placeholder value."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
