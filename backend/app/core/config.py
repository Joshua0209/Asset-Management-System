from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_string_list(value: object) -> object:
    """Accept either a JSON array (canonical) or a comma-separated string.

    pydantic-settings' default for `list[str]` env vars expects JSON
    (`["GET","POST"]`). Operators occasionally hand-edit `.env` files and
    write `GET,POST` instead, which silently mis-parsed as a single-element
    list `["GET,POST"]` (and then CORS would advertise a single bogus
    method). This validator normalises the comma-separated form before
    pydantic's own list parser runs, so both shapes work; pure JSON arrays
    pass through untouched.
    """
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    # JSON arrays start with `[` — let pydantic's default parser handle them.
    if stripped.startswith("["):
        return value
    if "," not in stripped:
        return value
    return [item.strip() for item in stripped.split(",") if item.strip()]


_StringList = Annotated[list[str], BeforeValidator(_parse_string_list)]


class Settings(BaseSettings):
    app_name: str = "Asset Management System API"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    database_url: str  # required — must be set via DATABASE_URL env var or .env
    cors_allowed_origins: _StringList = ["http://localhost:5173"]

    jwt_secret: str  # required — must be set via JWT_SECRET env var or .env
    jwt_algorithm: str = "HS256"
    jwt_access_token_expires_minutes: int = 720  # 12h, matches api-design §1.2 example

    # Bootstrap manager — seeded by scripts/seed_demo_data.py so the first
    # manager exists without a chicken-and-egg problem (Decision A2).
    bootstrap_manager_email: str = "admin@example.com"
    bootstrap_manager_password: str = "ChangeMe123"
    bootstrap_manager_name: str = "Bootstrap Manager"
    bootstrap_manager_department: str = "IT"

    repair_upload_dir: str = "uploads/repair-requests"

    # Rate limiting (slowapi, in-memory per-process — see
    # docs/system-design/05-phase2-architecture.md for the no-Redis decision).
    # `rate_limit_enabled=False` lets the test suite no-op the limiter without
    # patching every fixture; production must keep this true.
    rate_limit_enabled: bool = True
    rate_limit_authenticated: str = "100/minute"
    rate_limit_anonymous: str = "30/minute"
    # Image polling (`GET /images/{id}`) can legitimately fan out when a holder
    # browses several repair requests with attachments. Higher tier so a normal
    # session does not bump into the authenticated default.
    rate_limit_images: str = "300/minute"

    # CORS — defaults match the actual route surface. The "no DELETE / no
    # If-Match" invariant is enforced at the router site
    # (app/api/v1/router.py); when either appears, override these via env
    # rather than changing the source default.
    cors_allowed_methods: _StringList = ["GET", "POST", "PATCH", "OPTIONS"]
    cors_allowed_headers: _StringList = ["Authorization", "Content-Type"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # fields populated from env / .env by pydantic-settings
