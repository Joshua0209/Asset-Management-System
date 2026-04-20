from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Asset Management System API"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    database_url: str  # required — must be set via DATABASE_URL env var or .env
    cors_allowed_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # fields populated from env / .env by pydantic-settings
