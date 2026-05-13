"""Rate-limiting primitives.

Single source of truth for the slowapi `Limiter` and its `key_func`. We
decide the bucket per request:

* Valid `Authorization: Bearer <jwt>` header → ``user:<sub>``. The JWT is
  decoded inline (cheap, stateless) so we don't depend on FastAPI's auth
  dependency, which runs *after* slowapi middleware.
* Missing or malformed token → slowapi's ``get_remote_address``, which
  returns ``request.client.host``. Behind a load balancer that value is
  whatever uvicorn's ``ProxyHeadersMiddleware`` rewrote it to, gated by
  ``--forwarded-allow-ips`` (see
  ``docs/system-design/08-deployment-operations.md``). XFF spoofing is
  defeated by that single gate; this module deliberately does **not**
  re-read XFF here. A second reader would only matter if uvicorn's gate
  failed, and in that mode an application-layer reader is the attack
  surface (any client can forge their bucket key) — not a safety net.

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


def get_rate_limit_key(request: Request) -> str:
    """Return the bucket key for `request`.

    Authenticated requests bucket per user (so two users on the same NAT'd
    IP don't share a quota); anonymous requests bucket per client IP as
    resolved by uvicorn's ``ProxyHeadersMiddleware``.
    """
    token = _extract_bearer_token(request)
    if token is not None:
        try:
            payload = decode_access_token(token)
        except InvalidTokenError:
            # Garbage / expired token — treat as anonymous for limiting.
            return get_remote_address(request)
        except Exception:
            # Any unexpected decode error: log loudly, then degrade to IP
            # bucketing rather than 500-ing every request (key_func runs in
            # middleware on every hit). Never silent.
            logger.exception("Unexpected error decoding bearer token in key_func")
            return get_remote_address(request)
        return f"user:{payload.sub}"
    return get_remote_address(request)


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
