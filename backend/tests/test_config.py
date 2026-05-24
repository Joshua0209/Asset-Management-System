"""Settings-layer unit tests.

The CORS env parser accepts both JSON-array (canonical) and
comma-separated (operator-friendly) forms — without this normaliser, an
operator who hand-edits .env to write `CORS_ALLOWED_METHODS=GET,POST`
would silently end up with a single-element list `["GET,POST"]` and
preflight would advertise that bogus method to browsers.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import Settings, _parse_string_list


def test_parse_string_list_passes_through_actual_lists() -> None:
    assert _parse_string_list(["GET", "POST"]) == ["GET", "POST"]


def test_parse_string_list_parses_json_array_strings() -> None:
    """JSON-array strings should be parsed into real lists."""
    raw = '["GET", "POST"]'
    assert _parse_string_list(raw) == ["GET", "POST"]


def test_parse_string_list_returns_raw_value_for_malformed_json_array() -> None:
    """Malformed JSON-array strings fall back to the raw value.

    Pydantic's downstream list validator then raises a clear error rather
    than us silently swallowing a typo in the env file.
    """
    raw = '["GET", "POST"'  # missing closing bracket
    assert _parse_string_list(raw) == raw


def test_parse_string_list_parses_empty_json_array() -> None:
    """`"[]"` should reach pydantic as `[]`, not the literal string."""
    assert _parse_string_list("[]") == []


def test_parse_string_list_parses_single_element_json_array() -> None:
    """Single-element JSON arrays must still parse to a real list."""
    assert _parse_string_list('["GET"]') == ["GET"]


def test_parse_string_list_splits_comma_separated_strings() -> None:
    assert _parse_string_list("GET,POST,PATCH") == ["GET", "POST", "PATCH"]


def test_parse_string_list_strips_whitespace_around_items() -> None:
    assert _parse_string_list("GET, POST , PATCH ") == ["GET", "POST", "PATCH"]


def test_parse_string_list_drops_empty_items_from_trailing_comma() -> None:
    assert _parse_string_list("GET,POST,") == ["GET", "POST"]


def test_parse_string_list_returns_single_value_string_unchanged() -> None:
    """A single value with no comma is left for pydantic's default to handle."""
    assert _parse_string_list("GET") == "GET"


def test_parse_string_list_passes_non_strings_through() -> None:
    assert _parse_string_list(None) is None
    assert _parse_string_list(42) == 42


# ---------------------------------------------------------------------------
# CORS wildcard guard (P4) — docs/system-design/08-deployment-operations.md
# §"CORS Allowlist" forbids wildcard origins with `allow_credentials=True`
# (which the app sets unconditionally in main.py). The browser will reject
# `Access-Control-Allow-Origin: *` when credentials are sent, but a
# misconfigured backend that *reflects* the wildcard back is a real risk —
# guard it at config-load time so a stray CORS_ALLOWED_ORIGINS=["*"] cannot
# even boot the app.
# ---------------------------------------------------------------------------

_DB_URL = "sqlite:///:memory:"
_JWT_SECRET = "x" * 32  # noqa: S105


def test_settings_accepts_explicit_origin_list() -> None:
    """Baseline: a finite origin list still loads fine."""
    settings = Settings(
        database_url=_DB_URL,
        jwt_secret=_JWT_SECRET,
        cors_allowed_origins=["https://ams.example.com"],
    )
    assert settings.cors_allowed_origins == ["https://ams.example.com"]


def test_settings_rejects_bare_wildcard_origin() -> None:
    """Settings must refuse to load when `*` is in cors_allowed_origins.

    The app sends `allow_credentials=True`; a wildcard origin with
    credentials is unsafe (and rejected by browsers, but a reflected
    Access-Control-Allow-Origin from a misconfigured proxy would defeat
    the allowlist). Hard-fail at config load — same posture as a missing
    DATABASE_URL or JWT_SECRET.
    """
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            database_url=_DB_URL,
            jwt_secret=_JWT_SECRET,
            cors_allowed_origins=["*"],
        )
    msg = str(excinfo.value)
    assert "wildcard" in msg.lower() or "*" in msg
    assert "CORS_ALLOWED_ORIGINS" in msg or "cors_allowed_origins" in msg


def test_settings_rejects_wildcard_even_when_mixed_with_real_origins() -> None:
    """`["*", "https://ams.example.com"]` is just as unsafe as `["*"]` alone.

    The wildcard makes Starlette's CORSMiddleware echo Access-Control-Allow-
    Origin for every origin; the second entry becomes decorative. A
    naive validator that only rejected single-element lists would miss this.
    """
    with pytest.raises(ValidationError):
        Settings(
            database_url=_DB_URL,
            jwt_secret=_JWT_SECRET,
            cors_allowed_origins=["*", "https://ams.example.com"],
        )


def test_settings_rejects_wildcard_via_comma_form() -> None:
    """End-to-end: a comma-separated env value resolving to `*` is still blocked.

    Pins the interaction between `_parse_string_list` (which splits the
    comma-form into a real list) and the wildcard validator. The most
    realistic hostile shape — an operator hand-editing .env to
    `CORS_ALLOWED_ORIGINS=*,https://ams.example.com` thinking the explicit
    origin would "win" — must still be rejected.
    """
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            database_url=_DB_URL,
            jwt_secret=_JWT_SECRET,
            # str-form is valid input — `_parse_string_list` BeforeValidator
            # widens the field to accept str-or-list, mypy sees only `list[str]`.
            cors_allowed_origins="*,https://ams.example.com",  # type: ignore[arg-type]
        )
    msg = str(excinfo.value)
    assert "wildcard" in msg.lower() or "*" in msg


# ---------------------------------------------------------------------------
# DB-config completeness guard — production task definitions hydrate
# DB_HOST/DB_NAME plus secret-derived DB_USER/DB_PASSWORD. If a placeholder
# substitution breaks (e.g. an unset GitHub variable expanding to empty),
# we want to fail at config load rather than silently fall through to
# localhost defaults and produce a misleading runtime error.
# ---------------------------------------------------------------------------


def test_settings_accepts_full_database_url_alone() -> None:
    """`DATABASE_URL` is sufficient — component parts not required."""
    settings = Settings(database_url=_DB_URL, jwt_secret=_JWT_SECRET)
    assert settings.sqlalchemy_database_url == _DB_URL


def test_settings_accepts_complete_component_db_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production path: all four DB_* component parts present.

    The test suite's ``conftest`` seeds ``DATABASE_URL`` into ``os.environ``
    for the rest of the suite; the component-mode validator only runs when
    ``DATABASE_URL`` is unset, so we strip it (along with the local
    ``.env`` via ``_env_file=None``) for the DB-config tests.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]  # pydantic-settings runtime kwarg
        jwt_secret=_JWT_SECRET,
        db_host="rds.example.com",
        db_name="ams",
        db_user="ams_app",
        db_password="hunter2",  # noqa: S106  # test fixture, not a real credential
    )
    assert settings.sqlalchemy_database_url == (
        "mysql+pymysql://ams_app:hunter2@rds.example.com:3306/ams"
    )


def test_component_db_config_escapes_url_significant_secret_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Secrets Manager passwords may contain URL delimiters such as ``@``.

    Component-mode config must hand SQLAlchemy a valid URL where the password
    round-trips unchanged. Manual f-string URL construction mis-parses
    ``p@ss/word`` as URL structure instead of credentials.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        jwt_secret=_JWT_SECRET,
        db_host="rds.example.com",
        db_name="ams",
        db_user="ams_app",
        db_password="p@ss/word",  # noqa: S106
    )

    parsed = make_url(settings.sqlalchemy_database_url)

    assert parsed.host == "rds.example.com"
    assert parsed.username == "ams_app"
    assert parsed.password == "p@ss/word"
    assert parsed.database == "ams"


_DB_COMPONENT_FIELDS: tuple[tuple[str, str], ...] = (
    ("db_host", "DB_HOST"),
    ("db_name", "DB_NAME"),
    ("db_user", "DB_USER"),
    ("db_password", "DB_PASSWORD"),
)


@pytest.mark.parametrize(("missing_field", "expected_in_msg"), _DB_COMPONENT_FIELDS)
def test_settings_rejects_partial_component_db_config(
    monkeypatch: pytest.MonkeyPatch,
    missing_field: str,
    expected_in_msg: str,
) -> None:
    """Missing any one component part must fail at load, not boot with a default.

    Real-world failure mode: a broken GitHub Actions placeholder
    substitution leaves one of the DB_* vars empty. Parametrised over
    every component so a future refactor that drops one tuple entry from
    the validator's `missing` list is caught — a single-field check on
    DB_PASSWORD alone would have missed it.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    kwargs: dict[str, str] = {
        "db_host": "rds.example.com",
        "db_name": "ams",
        "db_user": "ams_app",
        "db_password": "hunter2",  # noqa: S106
    }
    del kwargs[missing_field]
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            jwt_secret=_JWT_SECRET,
            **kwargs,
        )
    msg = str(excinfo.value)
    assert expected_in_msg in msg
    assert "DATABASE_URL" in msg


def test_settings_rejects_empty_db_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing supplied at all — must fail at load."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, jwt_secret=_JWT_SECRET)  # type: ignore[call-arg]
    msg = str(excinfo.value)
    # All four component names should be enumerated to aid debugging.
    for name in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"):
        assert name in msg


def test_settings_treats_empty_database_url_string_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty `DATABASE_URL=""` must trigger component-mode validation.

    pydantic-settings reads `DATABASE_URL=""` as the literal empty
    string, not None. The validator's `if self.database_url:` truthy
    check correctly treats empty as "not set" today, but without a
    locked-in test a future refactor changing the guard to
    `is not None` would silently regress: production would then accept
    an empty URL, fall through SQLAlchemy URL parsing, and emit an
    opaque error far from the root cause. This is exactly the placeholder-
    substitution regression PR #63 is meant to prevent.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            database_url="",  # empty, mimics a broken placeholder substitution
            jwt_secret=_JWT_SECRET,
            # component parts deliberately missing — validator should require them
        )
    msg = str(excinfo.value)
    for name in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"):
        assert name in msg


# ---------------------------------------------------------------------------
# Credential redaction in dumps — locks the SecretStr posture so a future
# refactor demoting one of these fields back to plain ``str`` shows up as a
# test failure rather than a silent leak via structlog / startup-exception
# dumps that now flow to Grafana Cloud Loki via the OTel log exporter.
# ---------------------------------------------------------------------------


def test_settings_credentials_are_redacted_in_repr_and_dump() -> None:
    """``repr(settings)`` and ``model_dump()`` must not expose secret values.

    The SecretStr wrapper renders as ``'**********'`` in repr and as the
    SecretStr object in ``model_dump()``. With the OTel log exporter now
    in place, any exception path that logs the settings object would
    otherwise ship the JWT signing key + DB password + bootstrap manager
    password to Loki in cleartext. Locks the SecretStr contract for all
    four sensitive fields.
    """
    settings = Settings(
        database_url="mysql+pymysql://u:s3cret-db@db:3306/ams",
        jwt_secret="s3cret-jwt-key-do-not-leak",
        bootstrap_manager_email="boot@test.example",
        bootstrap_manager_password="s3cret-boot-password",  # noqa: S106
        db_password="s3cret-db-component",  # noqa: S106
    )
    rendered = repr(settings)
    for plaintext in (
        "s3cret-db",
        "s3cret-jwt-key-do-not-leak",
        "s3cret-boot-password",
        "s3cret-db-component",
    ):
        assert plaintext not in rendered, (
            f"plaintext credential {plaintext!r} leaked into repr(settings): "
            f"{rendered[:200]}"
        )
    dumped = settings.model_dump()
    # model_dump preserves SecretStr objects (their repr is masked too).
    for field in (
        "database_url",
        "jwt_secret",
        "bootstrap_manager_password",
        "db_password",
    ):
        value = dumped[field]
        if value is None:
            continue
        assert "s3cret" not in repr(value), (field, repr(value))
