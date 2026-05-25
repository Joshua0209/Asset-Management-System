"""Tests for the frontend init-failure beacon endpoint.

Locks the contract from
``docs/plans/observability-prod-migration-plan.md`` § "Frontend init
failure beacon" — Phase 3 added the browser-side OTLP SDK; the lack
of a backend-side counter for SDK init failures was the gap the
second review flagged. This module verifies:

* The endpoint accepts a well-formed beacon and increments the
  ``ams_frontend_observability_init_failures_total`` counter with
  the supplied ``kind`` attribute.
* It tolerates malformed bodies (no JSON, oversize payload, missing
  field) without 4xx-ing — fire-and-forget semantics on the browser
  side mean the counter's "malformed_beacon" sentinel kind is the
  only operator-visible signal that the beacon arrived but parsed
  wrong.
* It accepts both ``Content-Type: text/plain`` (the sendBeacon
  cross-origin-friendly default) and ``application/json`` so the
  endpoint is robust across browser variations.
* The endpoint is anonymous (no Authorization header required).
* It's excluded from the FastAPI OTel instrumentor's span generation
  — verified by the ``test_setup_metrics_passes_sanitize_and_excluded_urls``
  test in ``test_observability.py`` which asserts the ``excluded_urls``
  regex carries this path.
"""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from fastapi.testclient import TestClient
from opentelemetry import metrics as otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader


@pytest.fixture
def metric_reader() -> Iterable[InMemoryMetricReader]:
    """Install an InMemoryMetricReader-backed MeterProvider for this test.

    Same shape as ``test_observability.py``'s metric_reader fixture —
    duplicated here rather than promoted to conftest because conftest's
    module-level imports must run before any ``app.*`` import (see the
    long invariant block at the top of conftest.py), and the OTel SDK
    metric stack pulls in heavy modules that would re-shuffle that
    order. Per-file fixture keeps the conftest invariant intact.
    """
    from opentelemetry.metrics._internal import _PROXY_METER_PROVIDER

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    _PROXY_METER_PROVIDER.on_set_meter_provider(provider)
    try:
        yield reader
    finally:
        _PROXY_METER_PROVIDER.on_set_meter_provider(otel_metrics.NoOpMeterProvider())


def _kind_count(reader: InMemoryMetricReader, kind: str) -> float:
    """Sum the counter's data points for a specific ``kind`` attribute."""
    data = reader.get_metrics_data()
    if data is None:
        return 0.0
    total = 0.0
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name != "ams_frontend_observability_init_failures_total":
                    continue
                for dp in metric.data.data_points:
                    if dict(dp.attributes).get("kind") == kind:
                        total += float(dp.value)
    return total


def _beacon_rate_limited_count(reader: InMemoryMetricReader) -> float:
    """Sum the H1 visibility counter's data points."""
    data = reader.get_metrics_data()
    if data is None:
        return 0.0
    total = 0.0
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name != "ams_frontend_observability_beacon_rate_limited_total":
                    continue
                for dp in metric.data.data_points:
                    total += float(dp.value)
    return total


def _cross_origin_count(reader: InMemoryMetricReader) -> float:
    """Sum the M4 cross-origin counter's data points."""
    data = reader.get_metrics_data()
    if data is None:
        return 0.0
    total = 0.0
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name != "ams_frontend_observability_beacon_cross_origin_total":
                    continue
                for dp in metric.data.data_points:
                    total += float(dp.value)
    return total


def test_well_formed_text_plain_beacon_increments_counter_with_kind(
    client: TestClient,
    metric_reader: InMemoryMetricReader,
) -> None:
    """sendBeacon-shaped POST → 204 + counter ticks under reported kind."""
    response = client.post(
        "/api/v1/observability/client-error",
        content='{"kind":"observability_init_failed","message":"TypeError: foo"}',
        headers={"Content-Type": "text/plain;charset=utf-8"},
    )
    assert response.status_code == 204, response.text
    assert response.content == b""
    assert _kind_count(metric_reader, "observability_init_failed") == 1.0


def test_application_json_beacon_increments_counter(
    client: TestClient,
    metric_reader: InMemoryMetricReader,
) -> None:
    """The endpoint also accepts JSON Content-Type for same-origin callers."""
    response = client.post(
        "/api/v1/observability/client-error",
        json={"kind": "observability_init_failed", "message": "test"},
    )
    assert response.status_code == 204, response.text
    assert _kind_count(metric_reader, "observability_init_failed") == 1.0


def test_malformed_json_increments_malformed_beacon_kind(
    client: TestClient,
    metric_reader: InMemoryMetricReader,
) -> None:
    """A non-JSON body must NOT 4xx — counter records under sentinel kind.

    Fire-and-forget: the browser cannot see a 400, so returning one
    is wasted noise. Operators alert on the counter being non-zero;
    a ``malformed_beacon`` increment is the visible signal.
    """
    response = client.post(
        "/api/v1/observability/client-error",
        content="not json at all { broken }",
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 204, response.text
    assert _kind_count(metric_reader, "malformed_beacon") >= 1.0


def test_missing_required_field_falls_through_to_malformed(
    client: TestClient,
    metric_reader: InMemoryMetricReader,
) -> None:
    """``kind`` is required by the schema; absence → malformed_beacon."""
    response = client.post(
        "/api/v1/observability/client-error",
        json={"message": "only message no kind"},
    )
    assert response.status_code == 204, response.text
    assert _kind_count(metric_reader, "malformed_beacon") >= 1.0


def test_oversize_body_short_circuits_to_oversize_kind(
    client: TestClient,
    metric_reader: InMemoryMetricReader,
) -> None:
    """A 5+ KiB body never reaches JSON parsing — guards against abuse."""
    huge = "x" * (8 * 1024)
    response = client.post(
        "/api/v1/observability/client-error",
        content='{"kind":"x","message":"' + huge + '"}',
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 204, response.text
    assert _kind_count(metric_reader, "oversize_payload") >= 1.0


def test_empty_body_returns_204_without_counter_tick(
    client: TestClient,
    metric_reader: InMemoryMetricReader,
) -> None:
    """A zero-byte POST is silently ignored.

    Some browser implementations or proxies may strip the body on a
    sendBeacon retry; the endpoint must accept the call as a no-op
    rather than registering a misleading counter tick.
    """
    before = _kind_count(metric_reader, "observability_init_failed")
    before_malformed = _kind_count(metric_reader, "malformed_beacon")
    response = client.post(
        "/api/v1/observability/client-error",
        content="",
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 204, response.text
    assert _kind_count(metric_reader, "observability_init_failed") == before
    assert _kind_count(metric_reader, "malformed_beacon") == before_malformed


def test_user_agent_control_characters_are_stripped(
    client: TestClient,
    metric_reader: InMemoryMetricReader,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The User-Agent header is also passed through ``_CONTROL_CHARS_RE``.

    The existing control-character test covers ``kind`` and ``message``
    but not the third sanitised field. A regression that dropped the
    UA sanitisation (e.g. by removing the line entirely or replacing
    ``_CONTROL_CHARS_RE.sub`` with ``[:N]``) would land raw CR/LF in
    Loki labels — log injection into the operator's terminal /
    annotation viewer / Slack-bridge log forwarder. Pin the contract
    so a future refactor cannot quietly drop the UA scrubbing.
    """
    import logging as stdlib_logging

    poisoned_ua = "Mozilla/5.0\r\n\x00injected: fake-user-agent"
    with caplog.at_level(stdlib_logging.WARNING):
        response = client.post(
            "/api/v1/observability/client-error",
            json={"kind": "ua-probe", "message": "x"},
            headers={"User-Agent": poisoned_ua},
        )
    assert response.status_code == 204, response.text
    matched = [
        rec for rec in caplog.records
        if "Frontend observability init failure reported" in rec.message
    ]
    assert matched, [rec.message for rec in caplog.records]
    extras_ua = getattr(matched[0], "user_agent", "")
    for ch in ("\r", "\n", "\x00"):
        assert ch not in extras_ua, (ch, extras_ua)
    # The User-Agent's printable prefix is preserved (sanitisation is
    # one-to-one with '?', not strip — locks the length-preserving
    # contract documented at _CONTROL_CHARS_RE).
    assert "Mozilla/5.0" in extras_ua, extras_ua


def test_control_characters_are_stripped_from_logged_fields(
    client: TestClient,
    metric_reader: InMemoryMetricReader,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ASCII control bytes from anonymous senders are scrubbed to '?'.

    Pins the M2 contract: a payload containing CR/LF/null/etc. (which
    could trip a downstream Slack-bridge log forwarder, terminal
    rendering, or annotation viewer) is sanitized at the endpoint
    boundary before the structured log line is emitted. structlog
    itself escapes correctly into JSON, but defense in depth — the
    string lands in the Loki label without surprises for the
    operator's eyes.
    """
    import logging as stdlib_logging
    poisoned_message = "TypeError\r\n\x00\x07injected: rm -rf /"
    poisoned_kind = "init\rfail\n"
    with caplog.at_level(stdlib_logging.WARNING):
        response = client.post(
            "/api/v1/observability/client-error",
            json={"kind": poisoned_kind, "message": poisoned_message},
        )
    assert response.status_code == 204
    # Counter ticks under the SANITIZED kind, not the raw bytes.
    sanitized_kind = "init?fail?"
    assert _kind_count(metric_reader, sanitized_kind) == 1.0
    # The structured log line carries the sanitized strings — no raw
    # CR/LF/null bytes in either field.
    matched = [
        rec for rec in caplog.records
        if "Frontend observability init failure reported" in rec.message
    ]
    assert matched, [rec.message for rec in caplog.records]
    extras_kind = getattr(matched[0], "client_error_kind", "")
    extras_message = getattr(matched[0], "client_error_message", "")
    for ch in ("\r", "\n", "\x00", "\x07"):
        assert ch not in extras_kind, (ch, extras_kind)
        assert ch not in extras_message, (ch, extras_message)


def test_beacon_endpoint_enforces_dedicated_beacon_rate_limit(
    client: TestClient,
    metric_reader: InMemoryMetricReader,
) -> None:
    """The ``@limiter.limit(_beacon_rate_limit)`` decorator must
    actually fire on this endpoint.

    Locks the H1 contract: without this test, a regression that
    dropped ``@limiter.limit`` (or refactored ``_beacon_rate_limit``
    to return an ``unlimited`` string) would not fail anything in CI,
    leaving the counter ``ams_frontend_observability_init_failures_total``
    open to spam by any anonymous sender.

    Also pins the H1 visibility contract: when the cap fires, the
    ``ams_frontend_observability_beacon_rate_limited_total`` counter
    MUST tick — otherwise operators have no way to know that the
    init-failure counter is being silently truncated during a real
    outage (the browser cannot read the 429; sendBeacon discards it).

    The conftest sets ``RATE_LIMIT_BEACON=3/minute`` but disables
    the limiter globally. This test enables it for the duration of
    the request burst and asserts the 4th call lands as 429 with
    the project's error envelope shape + the visibility counter
    ticks for that 429.
    """
    from app.main import app

    original_enabled = app.state.limiter.enabled
    app.state.limiter.enabled = True
    # slowapi tracks per-key counters in module-level state; reset between
    # tests so a prior test that exhausted the bucket doesn't bleed.
    app.state.limiter.reset()
    try:
        for i in range(3):
            response = client.post(
                "/api/v1/observability/client-error",
                json={"kind": "rl-probe", "message": f"call {i}"},
            )
            assert response.status_code == 204, (i, response.text)
        before_rl = _beacon_rate_limited_count(metric_reader)
        blocked = client.post(
            "/api/v1/observability/client-error",
            json={"kind": "rl-probe", "message": "over the limit"},
        )
        assert blocked.status_code == 429, blocked.text
        body = blocked.json()
        assert body["error"]["code"] == "rate_limit_exceeded", body
        after_rl = _beacon_rate_limited_count(metric_reader)
        assert after_rl == before_rl + 1.0, (before_rl, after_rl)
    finally:
        app.state.limiter.enabled = original_enabled
        app.state.limiter.reset()


def test_frontend_beacon_url_is_canonical() -> None:
    """The hard-coded URL in ``frontend/src/observability.ts`` must
    match whatever path the backend actually mounts the beacon under.

    The frontend pins ``"/api/v1/observability/client-error"`` as a
    literal string constant — it CANNOT derive the prefix from the
    backend at build time because that would couple FE/BE Docker
    builds. So the only cross-side lock is THIS test: read the
    frontend's constant, compare to the backend's mounted route.
    A change to ``settings.api_v1_prefix`` (or a rename of the
    observability sub-router prefix) that forgot the frontend update
    will fail this test rather than silently render the beacon path
    unreachable in prod.
    """
    import re
    from pathlib import Path

    from app.core.config import get_settings
    from app.main import app

    repo_root = Path(__file__).resolve().parent.parent.parent
    fe_module = repo_root / "frontend" / "src" / "observability.ts"
    assert fe_module.exists(), fe_module

    text = fe_module.read_text(encoding="utf-8")
    match = re.search(
        r'_CLIENT_ERROR_BEACON_URL\s*=\s*"([^"]+)"',
        text,
    )
    assert match, "frontend constant _CLIENT_ERROR_BEACON_URL not found"
    fe_url = match.group(1)

    expected = (
        f"{get_settings().api_v1_prefix}/observability/client-error"
    )
    assert fe_url == expected, (fe_url, expected)

    # Also assert the route is actually mounted at that path on the
    # FastAPI app — catches the case where the test setting matches
    # the constant but the router is mis-included.
    mounted = {getattr(r, "path", None) for r in app.routes}
    assert expected in mounted, sorted(p for p in mounted if p)


def test_endpoint_accepts_anonymous_request(
    client: TestClient,
) -> None:
    """No Authorization header → still accepted.

    Init failures happen before the user authenticates; the endpoint
    must be reachable without a token. A regression that added auth
    deps would surface as a 401 here.
    """
    response = client.post(
        "/api/v1/observability/client-error",
        json={"kind": "anonymous", "message": ""},
    )
    assert response.status_code == 204, response.text


def test_cross_origin_beacon_skips_init_failure_counter(
    client: TestClient,
    metric_reader: InMemoryMetricReader,
) -> None:
    """M4 contract: a beacon with an Origin NOT in cors_allowed_origins
    must NOT tick the init-failure counter.

    ``sendBeacon`` with ``Content-Type: text/plain`` is a CORS simple
    request. The browser sends it cross-origin without a preflight,
    so the backend processes the body regardless of Origin. Without
    the M4 check, any attacker page can fire beacons from every IP
    in a botnet to inflate ``FRONTEND_OBS_FAILURES`` and trigger the
    alert rule continuously.

    Post-M4: the request still returns 204 (preserve fire-and-forget,
    don't reveal the filter rule), but the init-failure counter does
    NOT increment AND a dedicated cross-origin counter ticks so the
    operator can see the volume of off-origin probes.
    """
    before_init = _kind_count(metric_reader, "observability_init_failed")
    before_xo = _cross_origin_count(metric_reader)

    response = client.post(
        "/api/v1/observability/client-error",
        json={"kind": "observability_init_failed", "message": "attacker"},
        headers={"Origin": "https://attacker.example.com"},
    )

    assert response.status_code == 204, response.text
    # Init-failure counter MUST NOT tick for the cross-origin request.
    assert _kind_count(metric_reader, "observability_init_failed") == before_init
    # Cross-origin counter ticks instead.
    assert _cross_origin_count(metric_reader) == before_xo + 1.0


def test_same_origin_no_origin_header_still_increments_counter(
    client: TestClient,
    metric_reader: InMemoryMetricReader,
) -> None:
    """M4 contract: missing Origin header → treated as same-origin.

    The TestClient does not set an Origin header by default; same-origin
    XHR / fetch generally omit it. The endpoint must treat the absence
    of Origin as "same-origin, increment normally" — otherwise the M4
    filter would silently disable the entire beacon for the production
    same-origin deploy path.
    """
    before_init = _kind_count(metric_reader, "observability_init_failed")
    response = client.post(
        "/api/v1/observability/client-error",
        json={"kind": "observability_init_failed", "message": "same origin"},
    )
    assert response.status_code == 204, response.text
    assert _kind_count(metric_reader, "observability_init_failed") == before_init + 1.0


def test_allowlisted_origin_increments_counter(
    client: TestClient,
    metric_reader: InMemoryMetricReader,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M4 contract: an Origin IN cors_allowed_origins → normal flow.

    A split-origin deploy that correctly added the FE origin to
    CORS_ALLOWED_ORIGINS must still see the init-failure counter
    tick for legitimate beacons.
    """
    from app.core.config import get_settings

    # Conftest leaves cors_allowed_origins at its default
    # ["http://localhost:5173"]; assert the assumption then probe.
    assert "http://localhost:5173" in get_settings().cors_allowed_origins

    before_init = _kind_count(metric_reader, "observability_init_failed")
    response = client.post(
        "/api/v1/observability/client-error",
        json={"kind": "observability_init_failed", "message": "legit"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 204, response.text
    assert _kind_count(metric_reader, "observability_init_failed") == before_init + 1.0
