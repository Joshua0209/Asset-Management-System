"""CORS contract tests — locks down the audit decisions made in W4.

Specifically:

* Allowed origin gets `Access-Control-Allow-Origin` echo.
* Disallowed origin gets no CORS header.
* Preflight returns the *finite* configured methods/headers, not `*`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


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
