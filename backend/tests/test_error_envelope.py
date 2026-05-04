"""Tests for the global HTTPException → error-envelope handler in app/main.py.

The handler has two branches:

1. Structured `detail = {"code": ..., "message": ...}` → echoed verbatim into
   `error.code` / `error.message`. Endpoints use this to express granular 409
   codes (`invalid_transition`, `duplicate_request`) within the same status.

2. Otherwise → `error.code` derived from a status→code map and `error.message`
   from the raw string `detail` (or the code itself when detail isn't a string).

The granular-code path is covered end-to-end by `TestAssetTransition409ErrorCodes`
and `TestRepairRequest409ErrorCodes`. This file pins the *fallback* contract so a
future refactor of the handler doesn't accidentally break every other 4xx — and
also verifies that a malformed structured detail (missing `message`) is rejected
into the fallback rather than silently leaking through.
"""

from __future__ import annotations

from collections.abc import Callable, Generator

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.user import User, UserRole


_PROBE_PATH = "/__test__/raise"


@pytest.fixture
def probe_route() -> Generator[None, None, None]:
    """Register a one-shot route that re-raises a parametrized HTTPException.

    The route is removed after the test so it doesn't pollute the OpenAPI schema
    or leak into other tests' state.
    """
    holder: dict[str, HTTPException] = {}

    @app.get(_PROBE_PATH)
    def _probe() -> None:
        raise holder["exc"]

    yield from _yield_with_cleanup(holder)


def _yield_with_cleanup(holder: dict[str, HTTPException]) -> Generator[None, None, None]:
    try:
        # Hand the holder dict back via app.state so individual tests can mutate it.
        app.state.error_envelope_probe = holder
        yield
    finally:
        # Drop the route from the app so successive tests start clean.
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", None) != _PROBE_PATH
        ]
        app.state.error_envelope_probe = None


def _set_probe_exc(exc: HTTPException) -> None:
    holder: dict[str, HTTPException] = app.state.error_envelope_probe
    holder["exc"] = exc


class TestErrorEnvelopeHandler:
    def test_structured_detail_overrides_status_map(
        self, client: TestClient, probe_route: None
    ) -> None:
        _set_probe_exc(
            HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "duplicate_request", "message": "Already exists."},
            )
        )
        response = client.get(_PROBE_PATH)

        assert response.status_code == 409
        assert response.json() == {
            "error": {"code": "duplicate_request", "message": "Already exists."}
        }

    def test_string_detail_uses_status_map_code(
        self, client: TestClient, probe_route: None
    ) -> None:
        _set_probe_exc(
            HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found.",
            )
        )
        response = client.get(_PROBE_PATH)

        assert response.status_code == 404
        assert response.json() == {
            "error": {"code": "not_found", "message": "Asset not found."}
        }

    def test_unknown_status_falls_back_to_generic_error(
        self, client: TestClient, probe_route: None
    ) -> None:
        # 418 isn't in _STATUS_CODE_MAP — handler must default to "error".
        _set_probe_exc(HTTPException(status_code=418, detail="I'm a teapot."))
        response = client.get(_PROBE_PATH)

        assert response.status_code == 418
        assert response.json() == {"error": {"code": "error", "message": "I'm a teapot."}}

    def test_malformed_structured_detail_falls_back_to_status_map(
        self, client: TestClient, probe_route: None
    ) -> None:
        # Missing "message" key — handler must NOT trust a half-built dict;
        # it should drop into the status-map fallback so the response doesn't
        # leak the raw dict into `error.message`.
        _set_probe_exc(
            HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "duplicate_request"},  # no "message"
            )
        )
        response = client.get(_PROBE_PATH)

        assert response.status_code == 409
        body = response.json()["error"]
        assert body["code"] == "conflict"
        # message must not be the raw dict serialized as a string.
        assert "duplicate_request" not in body["message"] or body["message"] == "conflict"

    def test_real_404_endpoint_uses_envelope(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        db_session: Session,  # noqa: ARG002 — fixture pulled in for app.dependency_overrides
    ) -> None:
        # End-to-end smoke: a real 404 raised from `_not_found()` in the assets
        # endpoint should still travel through the fallback branch correctly
        # after the handler change.
        manager = make_user(role=UserRole.MANAGER)
        response = client.get(
            "/api/v1/assets/00000000-0000-0000-0000-000000000000",
            headers=auth_headers(manager),
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
