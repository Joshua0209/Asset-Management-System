"""Operator-facing endpoint for browser-side observability failures.

The browser OTLP SDK has no way to report its own init failure back
to Grafana Cloud — CORS denies the unauthenticated POST, the bundle
has no auth token (and must not, per the locked credentials-in-bundle
decision), and there is no in-bundle fallback channel. Without an
operator signal, a misconfigured prod build silently disables
browser tracing for every user, indistinguishable from
``VITE_OTEL_ENABLED=false``.

This endpoint receives a ``navigator.sendBeacon()`` POST from the
frontend's ``initObservability`` catch block, increments
``ams_frontend_observability_init_failures_total``, and logs a
structured warning — both surface via the OTel log + metric exporters
to Grafana Cloud, so the alert rule
``rate(ams_frontend_observability_init_failures_total[5m]) > 0``
catches the regression in the next deploy.

Design constraints:

* **Anonymous.** Init failure happens before user auth, so the
  endpoint must accept unauthenticated requests.
* **Rate-limited at a HIGHER tier than auth.** The beacon is
  fire-and-forget on the browser side — the 429 response is
  unreadable by ``sendBeacon`` — so a rate-limited beacon is
  otherwise invisible. The anonymous tier (30/min, sized for
  ``/auth/login``) would clip a real outage's signal by orders of
  magnitude. The dedicated ``rate_limit_beacon`` (600/min default)
  per-IP cap leaves plenty of headroom for legitimate failure
  storms while still bounding abuse, and the
  ``FRONTEND_OBS_BEACON_RATE_LIMITED`` counter ticks when the cap
  fires so the truncation itself is alertable.
* **No PII.** The payload accepts a short error kind + a truncated
  message string. The frontend explicitly truncates. The endpoint
  truncates again on receive as belt-and-suspenders.
* **Excluded from tracing.** The FastAPI instrumentor's
  ``excluded_urls`` block keeps this endpoint's own request from
  generating a span — a span that failed to export could trigger
  another beacon, runaway-feedback loop.
* **Origin-checked.** ``sendBeacon`` with ``Content-Type: text/plain``
  is a "simple request" under CORS — the browser sends it
  cross-origin WITHOUT a preflight, so the backend processes the
  body regardless of the ``Origin`` header. Without an explicit
  check, an attacker page can fire beacons from any IP in a botnet
  to inflate ``FRONTEND_OBS_FAILURES`` and trigger the alert rule
  continuously (alert fatigue, operator distraction). We check
  ``Origin`` against ``settings.cors_allowed_origins`` and skip the
  counter increment on mismatch — fire-and-forget semantics
  preserved (still 204), but the counter stays honest.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated

from fastapi import APIRouter, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.core.observability import (
    FRONTEND_OBS_BEACON_CROSS_ORIGIN,
    FRONTEND_OBS_FAILURES,
)
from app.core.rate_limit import limiter

logger = logging.getLogger(__name__)

# Strip ASCII control characters from anonymous-browser strings before they
# reach a log line. structlog's JSONRenderer escapes CR/LF correctly so
# log-injection into Loki itself is mitigated, but a malicious sender within
# the 30/min anonymous rate limit can post messages containing non-printable
# bytes that downstream Grafana annotations, Slack-bridge pipelines, or
# third-party log forwarders may not handle. Replace with '?' rather than
# strip to preserve the field's length (truncation cap is enforced
# elsewhere by Pydantic; preserving the count helps the operator notice
# tampered input).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _beacon_rate_limit() -> str:
    """Read the beacon rate-limit string per-request.

    Matches the pattern from ``endpoints/auth.py`` so a settings
    monkeypatch + cache-clear in tests is reflected here without a
    re-import dance. Distinct from ``rate_limit_anonymous`` because
    the beacon must tolerate failure-storm bursts; see module
    docstring "Rate-limited at a HIGHER tier than auth".
    """
    return get_settings().rate_limit_beacon


_MAX_MESSAGE_LEN = 500
_MAX_KIND_LEN = 64
_MAX_BODY_BYTES = 4 * 1024  # 4 KiB — generous; real beacon is <300 B.


class ClientErrorReport(BaseModel):
    """Schema for the frontend's failure beacon.

    Fields are deliberately permissive (any string) because the
    frontend's catch block has minimal context to populate — we
    accept whatever it sends, truncate, and surface to operators.
    Length caps prevent a malicious payload from exhausting log
    backend storage.
    """

    kind: Annotated[str, Field(min_length=1, max_length=_MAX_KIND_LEN)]
    message: Annotated[str, Field(default="", max_length=_MAX_MESSAGE_LEN)]


router = APIRouter()


@router.post(
    "/client-error",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    include_in_schema=False,  # internal observability surface
)
@limiter.limit(_beacon_rate_limit)
async def report_client_observability_failure(
    request: Request,
) -> Response:
    """Receive a frontend init-failure beacon, log + increment counter.

    Reads the body manually rather than using Pydantic's automatic
    request-body parsing because the frontend sends the beacon with
    ``Content-Type: text/plain``: ``navigator.sendBeacon()`` cross-
    origin only works without a CORS preflight when the Content-Type
    is in the simple-CORS set (``text/plain`` /
    ``application/x-www-form-urlencoded`` / ``multipart/form-data``).
    Same-origin requests work either way, but accepting ``text/plain``
    keeps the contract identical regardless of future deploy topology.

    The endpoint is fire-and-forget on the browser side, so we always
    return 204 — even for malformed payloads. Logging a 4xx that the
    browser can't read would be operator noise without diagnostic
    value; the counter going dark *is* the alert signal.
    """
    # Origin check (M4): sendBeacon with text/plain is a CORS simple
    # request, so the browser sends it cross-origin without preflight.
    # If the Origin header is set AND not in the configured
    # CORS_ALLOWED_ORIGINS allowlist, treat the request as cross-site
    # noise — return 204 (preserve fire-and-forget) but tick the
    # cross-origin counter INSTEAD of FRONTEND_OBS_FAILURES so the
    # init-failure alert rule stays honest. Same-origin requests (no
    # Origin header, or Origin equal to the request's own host) flow
    # through to the normal counter increment.
    origin = request.headers.get("origin")
    if origin and origin not in get_settings().cors_allowed_origins:
        FRONTEND_OBS_BEACON_CROSS_ORIGIN.add(1)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raw = await request.body()
    if not raw:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if len(raw) > _MAX_BODY_BYTES:
        # Don't even try to parse a massive payload — just count it as
        # a generic beacon. Real beacons fit in a few hundred bytes.
        FRONTEND_OBS_FAILURES.add(1, attributes={"kind": "oversize_payload"})
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        data = json.loads(raw)
        payload = ClientErrorReport.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError, UnicodeDecodeError):
        # Garbage body — still bump the counter under a sentinel kind so
        # operators see *something* went wrong on the client side, but
        # never crash the endpoint.
        FRONTEND_OBS_FAILURES.add(1, attributes={"kind": "malformed_beacon"})
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # Truncate again post-validate so a future schema relaxation can't
    # accidentally widen the field. Strip ASCII control characters from
    # both anonymous strings — see _CONTROL_CHARS_RE block at module top
    # for the rationale.
    kind = _CONTROL_CHARS_RE.sub("?", payload.kind[:_MAX_KIND_LEN])
    message = _CONTROL_CHARS_RE.sub("?", payload.message[:_MAX_MESSAGE_LEN])
    user_agent = _CONTROL_CHARS_RE.sub(
        "?", (request.headers.get("user-agent") or "")[:_MAX_MESSAGE_LEN]
    )
    logger.warning(
        "Frontend observability init failure reported via beacon.",
        extra={
            "client_error_kind": kind,
            "client_error_message": message,
            "user_agent": user_agent,
        },
    )
    FRONTEND_OBS_FAILURES.add(1, attributes={"kind": kind})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
