import json
import os
import socket
from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


def _default_replica_id() -> str:
    """Stable per-process replica label.

    Prefer ``HOSTNAME`` (set by Docker / ECS) so a single Grafana drop-down
    can list every replica without operator setup. Fall back to the local
    hostname, then a literal ``ams-backend-0`` so the field never blanks.
    """
    return os.environ.get("HOSTNAME") or socket.gethostname() or "ams-backend-0"


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
    # 1. **Full URL** (production / dev / docker-compose): set ``DATABASE_URL``
    #    to a complete SQLAlchemy URL like
    #    ``mysql+pymysql://user:pass@host:3306/ams``. Production ECS pulls
    #    this from the ``DATABASE_URL_SECRET_NAME`` Secrets Manager entry
    #    (see ``infra/ecs/backend-task-def.json``); local dev reads it from
    #    ``.env``. This is the canonical path.
    # 2. **Component parts** (legacy / local fallback): set ``DB_HOST``,
    #    ``DB_NAME``, ``DB_USER``, ``DB_PASSWORD``. Retained so existing
    #    local setups that predate the ``DATABASE_URL`` migration continue
    #    to boot, but new environments should use the full-URL form.
    #
    # When ``DATABASE_URL`` is set it wins; otherwise the component parts
    # are required and validated together by ``_require_database_config``.
    # No fallback to localhost defaults — silent prod misconfiguration was
    # the regression flagged in PR #63 review.
    # ``database_url`` and ``db_password`` are ``SecretStr`` so a
    # ``repr(settings)`` / ``model_dump()`` / structured-log dump of
    # ``Settings`` never leaks the production RDS password (or the
    # password embedded in a full DATABASE_URL). Pydantic coerces a
    # plain ``str`` env value into ``SecretStr`` at load time, and the
    # truthy check ``if self.database_url:`` continues to work because
    # ``SecretStr("")`` evaluates falsy (verified — pydantic-v2's
    # ``SecretStr`` defines ``__bool__`` from the wrapped value).
    database_url: SecretStr | None = None
    db_user: str | None = None
    db_password: SecretStr | None = None
    db_host: str | None = None
    # MySQL default. Pinned as `int` (not `str`) so pydantic rejects a typo
    # like `DB_PORT=abc` at load time instead of letting it through into
    # the URL where SQLAlchemy would surface a less actionable error.
    db_port: int = 3306
    db_name: str | None = None

    @property
    def sqlalchemy_database_url(self) -> str:
        """Render the full SQLAlchemy URL string.

        Only place the raw password leaves SecretStr — at the boundary
        SQLAlchemy needs to consume it. Callers should treat the
        returned string itself as sensitive (do not log it; the
        embedded password is in cleartext).
        """
        if self.database_url:
            return self.database_url.get_secret_value()
        # ``_require_database_config`` guarantees these are set when we get here.
        return URL.create(
            "mysql+pymysql",
            username=self.db_user,
            password=self.db_password.get_secret_value() if self.db_password else None,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        ).render_as_string(hide_password=False)

    cors_allowed_origins: _StringList = ["http://localhost:5173"]

    # ``SecretStr`` so a Settings dump never leaks the JWT signing key —
    # a 32-byte key in cleartext logs would let any reader mint tokens.
    # Plain str previously meant ``repr(settings)`` or ``model_dump()``
    # in a startup-error path would ship the key to Loki via the new
    # log exporter. Use ``.get_secret_value()`` at the JWT-encode/decode
    # boundary in app/core/security.py.
    jwt_secret: SecretStr  # required — must be set via JWT_SECRET env var or .env
    jwt_algorithm: str = "HS256"
    jwt_access_token_expires_minutes: int = 720  # 12h, matches api-design §1.2 example

    # Bootstrap manager — seeded by scripts/seed_demo_data.py so the first
    # manager exists without a chicken-and-egg problem (Decision A2).
    # `bootstrap_manager_email` and `_password` are REQUIRED (no defaults)
    # so a Secrets Manager injection failure surfaces at boot rather than
    # silently seeding `admin@example.com` / `ChangeMe123` into production.
    # Same posture as `jwt_secret`. `name` / `department` / `location` keep defaults
    # since they are not credentials. Password is ``SecretStr`` so a
    # log dump never carries the bootstrap manager's plaintext password.
    bootstrap_manager_email: str
    bootstrap_manager_password: SecretStr
    bootstrap_manager_name: str = "Bootstrap Manager"
    bootstrap_manager_department: str = "資產管理部"
    bootstrap_manager_location: str = "台北南港總部 8F"

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
    # The frontend init-failure beacon (`POST /observability/client-error`)
    # is fire-and-forget from the browser, so a 429 here silently truncates
    # the very signal it exists to surface: when a bad deploy breaks browser
    # OTel for 100% of users, the anonymous tier (30/min) clips beacons N
    # from a 1000x failure storm and the rate-rule fires with the wrong
    # magnitude. Use a far higher per-IP tier here, and pair with the
    # `FRONTEND_OBS_BEACON_RATE_LIMITED` counter so the truncation itself
    # is alertable when it fires.
    rate_limit_beacon: str = "600/minute"

    # CORS — defaults match the actual route surface. The "no DELETE / no
    # If-Match" invariant is enforced at the router site
    # (app/api/v1/router.py); when either appears, override these via env
    # rather than changing the source default.
    cors_allowed_methods: _StringList = ["GET", "POST", "PATCH", "OPTIONS"]
    cors_allowed_headers: _StringList = ["Authorization", "Content-Type"]

    # Observability (W6 Phase 3 of the prod migration plan) — OTLP-native,
    # pushes traces/metrics/logs/profiles direct to Grafana Cloud from both
    # dev and prod. All opt-in so a credential-less local boot stays quiet;
    # production flips OTEL_ENABLED + PYROSCOPE_ENABLED in the ECS task
    # definition. Endpoint defaults are empty rather than baked literals
    # (SonarCloud S5332); the `_require_observability_endpoints` validator
    # fails fast when an operator flips a flag without pointing it at a
    # collector. See backend/.env.example for canonical placeholders.
    otel_enabled: bool = False
    otel_endpoint: str = ""
    # OTLP exporter authentication. Grafana Cloud expects
    # ``Authorization=Basic <base64(instance_id:api_key)>``; the SDK splits
    # comma-separated ``key=value`` pairs into the gRPC metadata headers.
    # ``SecretStr`` so a ``repr(settings)`` / ``model_dump()`` / structured
    # log of the settings object does not leak the GC API key into Loki.
    # Call sites use ``.get_secret_value()`` at the exporter boundary.
    otel_exporter_otlp_headers: SecretStr = SecretStr("")
    pyroscope_enabled: bool = False
    pyroscope_server: str = ""
    # Pyroscope (Grafana Cloud) basic auth: username is the per-stack
    # numeric instance id; the token is the same Grafana Cloud API key
    # used for OTLP. Empty defaults keep the dev image's
    # ``pyroscope-io < 0.8.5`` historical kwargs-free configure() path
    # available, but >=0.8.5 (now pinned) accepts both kwargs as empty
    # strings without raising. Same SecretStr posture as the OTLP header.
    pyroscope_auth_token: SecretStr = SecretStr("")
    pyroscope_basic_auth_username: str = ""
    # Resource attribute stamped on every signal so dashboards can filter
    # local vs production traffic side-by-side. ``local`` matches what
    # developers see; the ECS task definition overrides to ``production``.
    environment: str = "local"
    # Hostname-derived per-process label. `default_factory` rather than a
    # module-import-time read so a unit test that swaps HOSTNAME via
    # `monkeypatch.setenv` and then constructs `Settings()` sees the swap.
    replica_id: str = Field(default_factory=_default_replica_id)
    # `text` for readable test logs; `json` for production. Validated to a
    # narrow set so a typo'd env var fails loud at boot.
    log_format: str = "json"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def _require_database_config(self) -> "Settings":
        """Fail fast when DB configuration is incomplete.

        Production passes ``DATABASE_URL`` from Secrets Manager
        (``DATABASE_URL_SECRET_NAME`` → ``infra/ecs/backend-task-def.json``).
        Legacy local setups may still supply the full ``DB_HOST`` /
        ``DB_NAME`` / ``DB_USER`` / ``DB_PASSWORD`` set instead. We refuse
        to boot with partial config (e.g. ``DB_HOST`` missing because of a
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

    @model_validator(mode="after")
    def _require_observability_endpoints(self) -> "Settings":
        """Fail fast when an observability flag is on but config is incomplete.

        The `otel_endpoint` / `pyroscope_server` defaults are intentionally
        empty so the source never ships a clear-text URL literal. When the
        operator flips a feature flag on they must also point it at a real
        collector — same posture as a missing DATABASE_URL or JWT_SECRET.

        Endpoints must be ``https://`` so a misconfigured env var cannot
        downgrade OTLP traffic to plaintext (which would leak the GC API key
        carried in ``OTEL_EXPORTER_OTLP_HEADERS``). The HTTP/2 OTLP gRPC
        SDK accepts ``http://`` too, but we refuse it: the only legitimate
        OTLP/Pyroscope targets in this project are GC's HTTPS endpoints.

        In any non-``local`` environment, ``OTEL_EXPORTER_OTLP_HEADERS``
        must also be set when ``otel_enabled`` is true — otherwise the
        OTLP exporter ships traffic that GC will silently 401, dropping
        every span/metric/log without an application-visible error.
        """
        if self.otel_enabled and not self.otel_endpoint:
            raise ValueError(
                "OTEL_ENABLED=true requires OTEL_ENDPOINT to be set "
                "(e.g. https://otlp-gateway-prod-<region>.grafana.net/otlp)."
            )
        if self.otel_enabled and not self.otel_endpoint.startswith("https://"):
            raise ValueError(
                f"OTEL_ENDPOINT must use https:// (got {self.otel_endpoint!r}). "
                "Plaintext OTLP would leak the GC API key in "
                "OTEL_EXPORTER_OTLP_HEADERS."
            )
        if self.pyroscope_enabled and not self.pyroscope_server:
            raise ValueError(
                "PYROSCOPE_ENABLED=true requires PYROSCOPE_SERVER to be set "
                "(e.g. https://profiles-prod-<region>.grafana.net)."
            )
        if self.pyroscope_enabled and not self.pyroscope_server.startswith("https://"):
            raise ValueError(
                f"PYROSCOPE_SERVER must use https:// (got {self.pyroscope_server!r})."
            )
        if (
            self.otel_enabled
            and self.environment != "local"
            and not self.otel_exporter_otlp_headers.get_secret_value()
        ):
            raise ValueError(
                f"OTEL_ENABLED=true in ENVIRONMENT={self.environment!r} requires "
                "OTEL_EXPORTER_OTLP_HEADERS to be set; the exporter would otherwise "
                "ship every span/metric/log with no auth and GC would silently 401."
            )
        # Pyroscope auth in non-local environments mirrors the OTLP check.
        # ``verify_observability_exports`` does NOT probe Pyroscope (the
        # pyroscope-io client has no synchronous flush/health surface), so
        # a missing token would only surface as silent 401s on the GC
        # ingest side and a dark profiling stream in production — same
        # silent-export-failure class the OTLP probe was added to close.
        # Refuse boot loudly here instead.
        if (
            self.pyroscope_enabled
            and self.environment != "local"
            and (
                not self.pyroscope_auth_token.get_secret_value()
                or not self.pyroscope_basic_auth_username
            )
        ):
            raise ValueError(
                f"PYROSCOPE_ENABLED=true in ENVIRONMENT={self.environment!r} requires "
                "both PYROSCOPE_AUTH_TOKEN and PYROSCOPE_BASIC_AUTH_USERNAME to be "
                "set; pyroscope-io would otherwise ship samples with empty basic-auth "
                "credentials and GC would silently 401, leaving profiling dark."
            )
        return self

    @field_validator("log_format")
    @classmethod
    def _validate_log_format(cls, value: str) -> str:
        """Refuse boot on a typo'd LOG_FORMAT.

        Two values supported: ``json`` (the default; structured prod logs)
        and ``text`` (pytest / interactive debug). Anything else points at
        operator confusion — fail loud rather than silently degrade.
        """
        allowed = {"json", "text"}
        if value not in allowed:
            raise ValueError(
                f"LOG_FORMAT={value!r} is not one of {sorted(allowed)}."
            )
        return value

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
