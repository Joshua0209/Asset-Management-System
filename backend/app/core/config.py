import json
from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_string_list(value: object) -> object:
    """Accept either a JSON array (canonical) or a comma-separated string.

    pydantic-settings' default for `list[str]` env vars expects JSON
    (`["GET","POST"]`). Operators occasionally hand-edit `.env` files and
    write `GET,POST` instead, which silently mis-parsed as a single-element
    list `["GET,POST"]` (and then CORS would advertise a single bogus
    method). This validator normalises the comma-separated form before
    pydantic's own list parser runs, so both shapes work; JSON-array
    strings are parsed via `json.loads` so pydantic receives a real list
    rather than a stringified one. Malformed JSON falls through to
    pydantic for a contextual `ValidationError` rather than being silently
    coerced.
    """
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped.startswith("["):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            # Let pydantic's list validator surface the offending input.
            return value
    if "," not in stripped:
        return value
    return [item.strip() for item in stripped.split(",") if item.strip()]


_StringList = Annotated[list[str], BeforeValidator(_parse_string_list)]


class Settings(BaseSettings):
    app_name: str = "Asset Management System API"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    # Database connection: two mutually exclusive modes.
    #
    # 1. **Full URL** (dev / docker-compose): set ``DATABASE_URL`` to a complete
    #    SQLAlchemy URL like ``mysql+pymysql://user:pass@host:3306/ams``. This
    #    is what ``.env`` and the local stack use.
    # 2. **Component parts** (production / ECS): set ``DB_HOST``, ``DB_NAME``,
    #    ``DB_USER``, ``DB_PASSWORD`` (the last two come from the
    #    RDS-managed Secrets Manager entry; see ``infra/ecs/README.md``).
    #    Letting ECS reference the RDS secret directly avoids manually
    #    copying the rotated password into a second secret.
    #
    # When ``DATABASE_URL`` is set it wins; otherwise the component parts
    # are required and validated together by ``_require_database_config``.
    # No fallback to localhost defaults — silent prod misconfiguration was
    # the regression flagged in PR #63 review.
    database_url: str | None = None
    db_user: str | None = None
    db_password: str | None = None
    db_host: str | None = None
    db_port: str = "3306"
    db_name: str | None = None

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        # ``_require_database_config`` guarantees these are set when we get here.
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

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
    # Image storage backend selector. "local" uses the disk-backed
    # LocalImageStorage (default for dev / docker compose); "s3" uses the
    # S3-backed adapter and requires repair_s3_bucket to be set. The
    # production ECS task definition sets this to "s3".
    repair_image_backend: str = "local"
    repair_s3_bucket: str = ""
    repair_s3_prefix: str = "repair-requests"

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

    @model_validator(mode="after")
    def _require_database_config(self) -> "Settings":
        """Fail fast when DB configuration is incomplete.

        Either ``DATABASE_URL`` *or* the full ``DB_HOST`` / ``DB_NAME`` /
        ``DB_USER`` / ``DB_PASSWORD`` set must be supplied. We refuse to
        boot with partial config (e.g. ``DB_HOST`` missing because of a
        broken placeholder substitution) instead of falling through to a
        bogus default that would silently try to connect to localhost.
        Same posture as the wildcard-CORS check above and the required
        ``JWT_SECRET`` field.
        """
        if self.database_url:
            return self
        missing = [
            name
            for name, value in (
                ("DB_HOST", self.db_host),
                ("DB_NAME", self.db_name),
                ("DB_USER", self.db_user),
                ("DB_PASSWORD", self.db_password),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Database configuration incomplete: set DATABASE_URL, or all "
                f"of DB_HOST/DB_NAME/DB_USER/DB_PASSWORD (missing: {', '.join(missing)})."
            )
        return self

    @field_validator("cors_allowed_origins")
    @classmethod
    def _reject_wildcard_origin(cls, origins: list[str]) -> list[str]:
        """Refuse to load when CORS_ALLOWED_ORIGINS contains ``"*"``.

        The app sends ``allow_credentials=True`` (app/main.py) — a wildcard
        origin combined with credentials is unsafe: modern browsers refuse
        the response, but a misconfigured proxy that *reflects* the wildcard
        back defeats the allowlist silently. Per
        docs/system-design/08-deployment-operations.md:52 ("Do not ship a
        wildcard origin to anything serving real users"), we hard-fail at
        config load — same posture as a missing DATABASE_URL or JWT_SECRET.

        Mixed lists like ``["*", "https://ams.example.com"]`` are equally
        unsafe because Starlette's CORSMiddleware short-circuits on the
        wildcard before checking the rest; we reject any list containing
        ``"*"`` rather than only single-element wildcards.
        """
        if "*" in origins:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS contains wildcard '*', which is unsafe "
                "with allow_credentials=True. List the explicit origins "
                "per docs/system-design/08-deployment-operations.md "
                "§'CORS Allowlist'."
            )
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # fields populated from env / .env by pydantic-settings
