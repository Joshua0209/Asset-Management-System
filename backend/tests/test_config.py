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

from app.core.config import Settings, _parse_string_list


def test_parse_string_list_passes_through_actual_lists() -> None:
    assert _parse_string_list(["GET", "POST"]) == ["GET", "POST"]


def test_parse_string_list_passes_json_array_strings_unchanged() -> None:
    """JSON-array strings should reach pydantic's default parser untouched."""
    raw = '["GET", "POST"]'
    assert _parse_string_list(raw) == raw


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

_REQUIRED_KW: dict[str, str] = {
    "database_url": "sqlite:///:memory:",
    "jwt_secret": "x" * 32,
}


def test_settings_accepts_explicit_origin_list() -> None:
    """Baseline: a finite origin list still loads fine."""
    settings = Settings(
        **_REQUIRED_KW,
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
            **_REQUIRED_KW,
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
            **_REQUIRED_KW,
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
            **_REQUIRED_KW,
            cors_allowed_origins="*,https://ams.example.com",
        )
    msg = str(excinfo.value)
    assert "wildcard" in msg.lower() or "*" in msg
