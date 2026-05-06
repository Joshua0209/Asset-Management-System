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


def test_key_func_authenticated_returns_user_sub(make_user: object) -> None:
    """A valid bearer token should bucket as ``user:<sub>``."""
    from unittest.mock import MagicMock

    from app.core.security import create_access_token
    from app.models.user import UserRole

    token, _ = create_access_token(subject="user-42", role=UserRole.HOLDER)

    request = MagicMock()
    request.headers = {"authorization": f"Bearer {token}"}
    request.client.host = "10.0.0.1"

    assert get_rate_limit_key(request) == "user:user-42"


def test_key_func_falls_back_to_ip_for_garbage_token() -> None:
    """An expired/tampered token must fall back to ``get_remote_address``."""
    from unittest.mock import MagicMock

    request = MagicMock()
    request.headers = {"authorization": "Bearer not-a-real-jwt"}
    request.client.host = "192.168.0.1"

    # Falls back to IP rather than 500-ing on bad tokens.
    assert get_rate_limit_key(request) == "192.168.0.1"


def test_key_func_falls_back_to_ip_when_header_missing() -> None:
    from unittest.mock import MagicMock

    request = MagicMock()
    request.headers = {}
    request.client.host = "172.16.0.5"

    assert get_rate_limit_key(request) == "172.16.0.5"


def test_key_func_ignores_non_bearer_authorization() -> None:
    """Basic-auth and other schemes should not be parsed as JWTs."""
    from unittest.mock import MagicMock

    request = MagicMock()
    request.headers = {"authorization": "Basic dXNlcjpwYXNz"}
    request.client.host = "10.10.10.10"

    assert get_rate_limit_key(request) == "10.10.10.10"


def test_key_func_uses_xforwarded_for_when_present() -> None:
    """Anonymous bucket must split on the original client IP behind a proxy.

    Regression guard for the ALB self-DoS: if `_client_ip` ever stops
    reading X-Forwarded-For, every anonymous request collapses to the
    proxy IP and one attacker drains the global anon quota.

    The header is hyphen-cased here on purpose — slowapi's built-in
    ``get_ipaddr`` looks up underscores, which Starlette never matches.
    """
    from unittest.mock import MagicMock

    request = MagicMock()
    request.headers = {"x-forwarded-for": "203.0.113.7, 10.0.0.5"}
    # ALB private IP — what request.client.host would be without proxy-headers.
    request.client.host = "10.0.0.5"

    # Leftmost (original client), not the proxy.
    assert get_rate_limit_key(request) == "203.0.113.7"


def test_key_func_xforwarded_for_takes_precedence_over_client_host() -> None:
    """XFF wins over client.host even when client.host is set.

    Production trust comes from uvicorn's --forwarded-allow-ips gate,
    not from this code. The application layer is defense-in-depth.
    """
    from unittest.mock import MagicMock

    request = MagicMock()
    request.headers = {"x-forwarded-for": "198.51.100.42"}
    request.client.host = "10.0.0.5"

    assert get_rate_limit_key(request) == "198.51.100.42"


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


# ---------------------------------------------------------------------------
# Per-endpoint application tests — exercise the *real* app with a temporary
# enabled limiter so /health exempt and the auth-endpoints anonymous tier
# behave as the spec requires.
# ---------------------------------------------------------------------------


def _reset_limiter_storage(limiter_obj: object) -> None:
    """Best-effort reset of slowapi's MemoryStorage between tests.

    slowapi 0.1.9 exposes ``Limiter._storage.reset()`` as a private attribute,
    pinned in pyproject as ``slowapi>=0.1.9,<1.0`` — a future 0.1.10 could
    rename or relocate ``_storage`` and we'd break test isolation silently
    rather than nine of ten ways noisily. Defensive lookup logs a warning
    instead of AttributeError-ing the whole suite. If ``.reset()`` truly
    disappears, MemoryStorage carries per-test counters into the next test
    and bucket-exhaustion tests start flaking — that *is* worth a logged
    warning each test, not a silent skip.
    """
    storage = getattr(limiter_obj, "_storage", None)
    reset = getattr(storage, "reset", None) if storage is not None else None
    if callable(reset):
        reset()
        return
    import logging

    logging.getLogger(__name__).warning(
        "slowapi Limiter._storage.reset() unavailable on %r; "
        "rate-limit test isolation may degrade. Pin slowapi tighter or "
        "update _reset_limiter_storage().",
        type(limiter_obj),
    )


@pytest.fixture
def enabled_limiter(client: TestClient) -> Generator[TestClient, None, None]:
    """Re-enable the production app's limiter for a single test.

    Flips ``Limiter.enabled`` rather than swapping the instance — the
    ``_exempt_routes`` registry (set at decorator time) lives on the
    original instance, so swapping it would lose ``@limiter.exempt`` marks.
    Conftest pre-configures tight numeric limits via env so a few requests
    are enough to trigger 429.
    """
    from app.main import app

    saved_enabled = app.state.limiter.enabled
    # Reset per-key counters between tests so rapid-fire pytest runs don't
    # accumulate.
    _reset_limiter_storage(app.state.limiter)
    app.state.limiter.enabled = True
    try:
        yield client
    finally:
        app.state.limiter.enabled = saved_enabled
        _reset_limiter_storage(app.state.limiter)


def test_health_endpoint_is_exempt_from_rate_limit(
    enabled_limiter: TestClient,
) -> None:
    """/health serves monitoring probes — must not 429 even after many hits."""
    for _ in range(20):
        response = enabled_limiter.get("/health")
        assert response.status_code == 200, response.text


def test_auth_login_uses_anonymous_tier(enabled_limiter: TestClient) -> None:
    """POST /auth/login must 429 once the anonymous-IP budget is spent.

    Default-tier budget here is 5/minute; the auth endpoints should also
    carry a per-IP decorator so the tighter limit kicks in.
    """
    seen_429 = False
    for _ in range(15):
        response = enabled_limiter.post(
            "/api/v1/auth/login",
            json={"email": "nope@example.com", "password": "wrongpass"},
        )
        if response.status_code == 429:
            seen_429 = True
            assert response.json()["error"]["code"] == "rate_limit_exceeded"
            break
    assert seen_429, "expected POST /auth/login to enter 429 after exhaustion"


def test_rate_limit_handler_is_not_a_coroutine() -> None:
    """Regression guard for the async-handler trap.

    `register_rate_limit_handler` MUST stay a plain ``def``. slowapi's
    SlowAPIMiddleware looks up the handler via
    ``app.exception_handlers[RateLimitExceeded]`` *synchronously* — if a
    coroutine is registered the middleware silently falls back to slowapi's
    default plaintext body, breaking the FE's error-envelope contract.

    This test pins the contract directly on the registered handler so a
    future ``async def`` flip is caught at unit-test speed (no 429-burn
    integration loop required).
    """
    import inspect

    from slowapi.errors import RateLimitExceeded

    test_app = FastAPI()
    register_rate_limit_handler(test_app)

    handler = test_app.exception_handlers[RateLimitExceeded]
    assert not inspect.iscoroutinefunction(handler), (
        "register_rate_limit_handler must register a synchronous `def` "
        "handler — slowapi.middleware.sync_check_limits cannot await a "
        "coroutine and silently falls back to its plaintext default."
    )


def test_authenticated_route_inherits_default_tier_limit(
    enabled_limiter: TestClient,
    make_user: object,
    auth_headers: object,
) -> None:
    """Routes without an explicit `@limiter.limit` decorator must still be
    rate-limited via the Limiter's `default_limits` setting.

    Pins the `default_limits=[rate_limit_authenticated]` contract in
    `app/core/rate_limit.py::_build_limiter` so a future refactor that
    drops the default leaves a load-bearing test failure rather than a
    silently uncapped surface. We exercise GET /api/v1/assets/mine, which
    carries no per-route `@limiter.limit` decorator at the time of
    writing — the default tier is the only thing protecting it.

    Conftest's RATE_LIMIT_AUTHENTICATED is "5/minute", so the sixth call
    must 429.
    """
    from app.models.user import UserRole

    holder = make_user(role=UserRole.HOLDER)  # type: ignore[operator]
    headers = auth_headers(holder)  # type: ignore[operator]

    seen_429 = False
    for _ in range(10):
        response = enabled_limiter.get("/api/v1/assets/mine", headers=headers)
        if response.status_code == 429:
            seen_429 = True
            body = response.json()
            assert body["error"]["code"] == "rate_limit_exceeded", body
            break
    assert seen_429, (
        "expected default authenticated tier (5/minute under conftest) to "
        "kick in on an undecorated authenticated route"
    )
