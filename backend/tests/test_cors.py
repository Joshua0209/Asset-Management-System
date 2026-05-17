"""CORS contract tests — locks down the audit decisions made in W4.

Specifically:

* Allowed origin gets `Access-Control-Allow-Origin` echo.
* Disallowed origin gets no CORS header.
* Preflight returns the *finite* configured methods/headers, not `*`.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.models.user import User


def test_allowed_origin_is_echoed(client: TestClient) -> None:
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_disallowed_origin_gets_no_cors_header(client: TestClient) -> None:
    response = client.get(
        "/health",
        headers={"Origin": "https://evil.example.com"},
    )
    # Endpoint still resolves, but no CORS header echo for the bad origin.
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") is None


def test_preflight_returns_finite_methods_not_wildcard(client: TestClient) -> None:
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization",
        },
    )
    assert response.status_code == 200
    allow_methods = response.headers.get("access-control-allow-methods", "")
    # Must NOT be the lazy wildcard.
    assert allow_methods != "*"
    # Must include the verbs we actually use.
    methods = {m.strip().upper() for m in allow_methods.split(",")}
    assert {"GET", "POST", "PATCH", "OPTIONS"}.issubset(methods)
    # Must NOT advertise verbs we don't serve.
    assert "DELETE" not in methods


def test_preflight_returns_finite_headers_not_wildcard(client: TestClient) -> None:
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert response.status_code == 200
    allow_headers = response.headers.get("access-control-allow-headers", "")
    assert allow_headers != "*"
    headers = {h.strip().lower() for h in allow_headers.split(",")}
    assert "authorization" in headers
    assert "content-type" in headers


def test_auth_login_200_echoes_allowed_origin(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    """The actual cross-origin POST (not just the preflight) must carry
    ``Access-Control-Allow-Origin`` on success. PR #60 fixed the 500 that
    was preventing CORSMiddleware from attaching this header; pin the fix
    so a regression to a non-Response return on the auth endpoints can't
    silently re-break the FE.
    """
    make_user(email="cors@example.com", password="Password123")
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "cors@example.com", "password": "Password123"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_auth_login_401_echoes_allowed_origin(client: TestClient) -> None:
    """Same guarantee on the error path: a wrong-credentials 401 still flows
    through HTTPException + middleware, and the browser still needs ACAO to
    surface the response body to JS. Without this, the FE's "invalid login"
    toast would silently fail to render under CORS.
    """
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "Whatever123"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 401
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_preflight_from_disallowed_origin_is_rejected(client: TestClient) -> None:
    """A preflight from an unallowlisted origin must NOT echo CORS headers.

    Starlette's CORSMiddleware short-circuits the preflight when the origin
    isn't in `allow_origins`, returning a 400 (or omitting the
    Access-Control-Allow-Origin header). Either way, the browser's
    preflight check fails and the cross-origin POST never fires.

    Pins the audit decision: only listed origins get CORS — wildcards in
    `allow_origins` are explicitly out of scope per
    docs/system-design/08-deployment-operations.md.
    """
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    # Two acceptable shapes: 400 from CORSMiddleware's reject path, or any
    # status without an ACAO echo. Both stop the browser from completing
    # the cross-origin request. We assert the *only* contract that matters
    # to a browser: no Access-Control-Allow-Origin echo for a bad origin.
    assert response.headers.get("access-control-allow-origin") != "https://evil.example.com"
    # And specifically not a wildcard (which would defeat the allowlist).
    assert response.headers.get("access-control-allow-origin") != "*"
