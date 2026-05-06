"""Settings-layer unit tests.

The CORS env parser accepts both JSON-array (canonical) and
comma-separated (operator-friendly) forms — without this normaliser, an
operator who hand-edits .env to write `CORS_ALLOWED_METHODS=GET,POST`
would silently end up with a single-element list `["GET,POST"]` and
preflight would advertise that bogus method to browsers.
"""

from __future__ import annotations

from app.core.config import _parse_string_list


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
