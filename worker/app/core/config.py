"""Worker settings — Phase 2 Redis / S3 connectivity (no Celery tasks yet)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
