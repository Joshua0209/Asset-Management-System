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
