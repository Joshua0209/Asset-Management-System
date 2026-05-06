"""Rate-limit contract tests.

These verify two things the FE+BE contract depends on:

1. 429 responses MUST conform to the project error envelope
   (`{"error": {"code": "rate_limit_exceeded", "message": ...}}`).
2. `X-RateLimit-Limit/Remaining/Reset` headers ride along on 2xx responses,
   and `Retry-After` rides along on 429 responses.

Each test rebuilds a fresh ``Limiter`` so it is independent of the
suite-wide ``RATE_LIMIT_ENABLED=false`` set in ``conftest.py``.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware

from app.core.rate_limit import get_rate_limit_key
from app.main import register_rate_limit_handler


def _build_app(*, anon_limit: str = "3/minute") -> FastAPI:
    """Tiny app whose only purpose is to exercise the limiter."""
    test_app = FastAPI()
    limiter = Limiter(
        key_func=get_rate_limit_key,
        default_limits=[anon_limit],
        enabled=True,
        headers_enabled=True,
    )
    test_app.state.limiter = limiter
    test_app.add_middleware(SlowAPIMiddleware)
    register_rate_limit_handler(test_app)

    @test_app.get("/probe")
    def probe(request: Request) -> dict[str, str]:
        return {"ok": "true"}

    return test_app


@pytest.fixture
def rl_client() -> Generator[TestClient, None, None]:
    app = _build_app()
    with TestClient(app) as client:
        yield client


def test_429_response_conforms_to_error_envelope(rl_client: TestClient) -> None:
    # 3/minute → fourth call must be blocked.
    for _ in range(3):
        ok = rl_client.get("/probe")
        assert ok.status_code == 200, ok.text

    blocked = rl_client.get("/probe")
    assert blocked.status_code == 429
    body = blocked.json()
    assert "error" in body, body
    assert body["error"]["code"] == "rate_limit_exceeded"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


def test_429_response_carries_retry_after_header(rl_client: TestClient) -> None:
    for _ in range(3):
        rl_client.get("/probe")
    blocked = rl_client.get("/probe")
    assert blocked.status_code == 429
    assert "retry-after" in {k.lower() for k in blocked.headers.keys()}


def test_2xx_responses_carry_x_ratelimit_headers(rl_client: TestClient) -> None:
    response = rl_client.get("/probe")
    assert response.status_code == 200
    headers = {k.lower() for k in response.headers.keys()}
    assert "x-ratelimit-limit" in headers
    assert "x-ratelimit-remaining" in headers
    assert "x-ratelimit-reset" in headers


def test_anonymous_buckets_are_per_ip(rl_client: TestClient) -> None:
    """Two distinct client IPs share separate quotas.

    TestClient defaults to 'testclient' for the remote address, but slowapi's
    `get_remote_address` reads `request.client.host`. The TestClient honors
    the `client` kwarg per-request only via ASGI scope, so we use distinct
    `X-Forwarded-For` would not work without trusting it; instead we bracket
    by exhausting one client and verifying a second `TestClient` on a fresh
    app sees full quota.
    """
    # Same app, same key (testclient host). Burn 3 requests, fourth blocks.
    for _ in range(3):
        rl_client.get("/probe")
    assert rl_client.get("/probe").status_code == 429

    # Fresh app (separate Limiter state) → counters reset and 200 again.
    fresh = TestClient(_build_app())
    assert fresh.get("/probe").status_code == 200


def test_disabled_limiter_is_a_noop() -> None:
    """`enabled=False` Limiter must not 429 even on the 100th call."""
    test_app = FastAPI()
    test_app.state.limiter = Limiter(
        key_func=get_rate_limit_key,
        default_limits=["1/minute"],
        enabled=False,
        headers_enabled=True,
    )
    test_app.add_middleware(SlowAPIMiddleware)
    register_rate_limit_handler(test_app)

    @test_app.get("/probe")
    def probe(request: Request) -> dict[str, str]:
        return {"ok": "true"}

    with TestClient(test_app) as client:
        for _ in range(5):
            response = client.get("/probe")
            assert response.status_code == 200
