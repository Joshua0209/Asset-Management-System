"""Rate-limiting primitives.

Single source of truth for the slowapi `Limiter` and its `key_func`. We
decide the bucket per request:

* Valid `Authorization: Bearer <jwt>` header → ``user:<sub>``. The JWT is
  decoded inline (cheap, stateless) so we don't depend on FastAPI's auth
  dependency, which runs *after* slowapi middleware.
* Missing or malformed token → fall back to the resolved client IP (see
  ``_client_ip`` for the X-Forwarded-For handling behind a load balancer).

Tests can no-op all limits by setting ``RATE_LIMIT_ENABLED=false`` — see
``Settings.rate_limit_enabled``.
"""

from __future__ import annotations

import logging

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.security import InvalidTokenError, decode_access_token

_BEARER_PREFIX = "bearer "

logger = logging.getLogger(__name__)


def _extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header is None:
        return None
    if not header.lower().startswith(_BEARER_PREFIX):
        return None
    return header[len(_BEARER_PREFIX):].strip() or None


def _client_ip(request: Request) -> str:
    """Resolve the originating client IP for rate-limit bucketing.

    Behind an ALB / reverse proxy ``request.client.host`` is the proxy's IP,
    so every anonymous request collapses into a single bucket and the limiter
    becomes a self-DoS. Two complementary mitigations:

    1. **Production canonical path** — run uvicorn with
       ``--proxy-headers --forwarded-allow-ips=<ALB CIDR>``. uvicorn's
       ``ProxyHeadersMiddleware`` then rewrites ``request.client.host`` from
       the X-Forwarded-For chain *only* when the immediate hop is in the
       trusted CIDR, so spoofed XFF headers from arbitrary clients are
       ignored. See ``docs/system-design/08-deployment-operations.md``.

    2. **Defense-in-depth** — read X-Forwarded-For directly here, leftmost
       value (the original client per RFC 7239 conventions). Note: slowapi's
       built-in ``get_ipaddr`` looks up ``request.headers["X_FORWARDED_FOR"]``
       (underscores), but Starlette normalises header names to hyphens, so
       that lookup silently returns the proxy IP. We use the hyphen form
       explicitly. This branch trusts XFF unconditionally — that is safe
       *only* when uvicorn's proxy-headers gate is in place upstream.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Comma-separated chain: leftmost is the original client.
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    return get_remote_address(request)


def get_rate_limit_key(request: Request) -> str:
    """Return the bucket key for `request`.

    Authenticated requests bucket per user (so two users on the same NAT'd
    IP don't share a quota); anonymous requests bucket per resolved client IP.
    """
    token = _extract_bearer_token(request)
    if token is not None:
        try:
            payload = decode_access_token(token)
        except InvalidTokenError:
            # Garbage / expired token — treat as anonymous for limiting.
            return _client_ip(request)
        except Exception:
            # Any unexpected decode error: log loudly, then degrade to IP
            # bucketing rather than 500-ing every request (key_func runs in
            # middleware on every hit). Never silent.
            logger.exception("Unexpected error decoding bearer token in key_func")
            return _client_ip(request)
        return f"user:{payload.sub}"
    return _client_ip(request)


def _build_limiter() -> Limiter:
    settings = get_settings()
    return Limiter(
        key_func=get_rate_limit_key,
        default_limits=[settings.rate_limit_authenticated],
        # `enabled=False` makes every `.limit(...)` decorator a no-op so the
        # rest of the test suite isn't timing-sensitive.
        enabled=settings.rate_limit_enabled,
        headers_enabled=True,
    )


limiter = _build_limiter()
