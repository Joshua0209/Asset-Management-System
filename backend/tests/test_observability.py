"""Backend observability smoke tests (W6 Phase 3, OTLP-native).

These verify the contract from
``docs/plans/observability-prod-migration-plan.md`` § Phase 3:

* Optimistic-conflict counter increments on a 409 raised by an
  asset/repair-request endpoint, keyed by ``{endpoint, code}``.
* FSM-transition counter increments on a successful repair-request
  state change, keyed by ``{state_from, state_to, asset_kind}``.
* Structlog JSON renderer emits ``trace_id`` when a span is active.
* ``setup_metrics_exporter`` installs a working ``MeterProvider`` and
  the module-level counters route into it.
* ``setup_log_exporter`` installs a working ``LoggerProvider`` and
  the structlog → OTel logs bridge stamps the active span's
  ``trace_id`` on emitted ``LogRecord``s.
* ``maybe_setup_profiling`` calls ``pyroscope.configure`` regardless
  of ``environment`` (locked decision 5 reversal — Pyroscope is now
  on in production).
* New ``Settings`` observability fields exist with safe defaults
  (off in tests, opt-in via env in deploys).

There is no ``/metrics`` HTTP route to test any more — Phase 3 deleted
it. Counter behaviour is verified by attaching an
``InMemoryMetricReader`` to a real ``MeterProvider`` and reading the
captured ``MetricsData`` directly.
"""

from __future__ import annotations

import itertools
import logging
import os
from collections.abc import Callable, Iterable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from opentelemetry import metrics as otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole

_REPAIR_ID_COUNTER = itertools.count(80001)


def _unique_repair_id() -> str:
    """Local counter so each test row satisfies the UNIQUE constraint on
    ``RepairRequest.repair_id`` without colliding with other suites that
    share the module-level counter in ``test_repair_requests``.
    """
    return f"REP-OBS-{next(_REPAIR_ID_COUNTER):05d}"


# ---------------------------------------------------------------------------
# OTel meter-provider plumbing
#
# A fresh InMemoryMetricReader per fixture call so cross-test counters do
# not leak. The module-level ProxyCounter instances created at import
# time resolve to whatever MeterProvider is current at .add() time, so
# installing a new provider per test gives each test a clean ledger.
# ---------------------------------------------------------------------------


@pytest.fixture
def metric_reader() -> Iterable[InMemoryMetricReader]:
    """Install an InMemoryMetricReader-backed MeterProvider for this test.

    OTel's public ``metrics.set_meter_provider`` is set-once per process,
    which is the right invariant for production (``setup_metrics_exporter``
    runs exactly once at startup) but blocks per-test isolation. We reach
    into the SDK's ``_PROXY_METER_PROVIDER`` and re-call
    ``on_set_meter_provider`` directly: that re-binds the module-level
    ``_ProxyCounter`` instances created at import time to a fresh real
    counter from the new provider. The previous fixture's provider is
    discarded; nothing else in the suite reads its reader.
    """
    from opentelemetry.metrics._internal import _PROXY_METER_PROVIDER

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    _PROXY_METER_PROVIDER.on_set_meter_provider(provider)
    try:
        yield reader
    finally:
        # Rebind to the SDK's default no-op so a later test that does NOT
        # use this fixture sees a fresh proxy state, not the now-stale
        # provider whose reader we just discarded.
        _PROXY_METER_PROVIDER.on_set_meter_provider(otel_metrics.NoOpMeterProvider())


@pytest.fixture(autouse=True)
def _reset_observability_module_state() -> Iterable[None]:
    """Reset observability.py + OTel global state per test.

    Two layers of state get cleared:

    1. **observability.py module state.** The setup_log_exporter /
       setup_metrics_exporter / setup_tracing installers flip one-shot
       module flags so a second call inside the same process is a no-op
       (production runs each exactly once; without the guard a re-import
       would leak background exporter threads). Tests need to re-enter
       the install path each time, so the flags reset around every test.
       Also clears ``_TRACE_CONTEXT_WARNED`` so a per-test span misconfig
       surfaces fresh, and ``_RESOURCE_CACHE`` so each test sees a Resource
       computed against its own monkeypatched settings.

    2. **OTel global tracer/logger set-once.** ``trace.set_tracer_provider``
       and ``_logs.set_logger_provider`` are process-wide set-once via an
       internal ``Once`` flag. The first test that calls them succeeds;
       subsequent tests get a warning and the install no-ops, so their
       spans/logs end up routed to the *prior* test's provider. Resetting
       the ``_done`` flag (and the ``_TRACER_PROVIDER`` / ``_LOGGER_PROVIDER``
       globals) per test lets each test install its own in-memory
       exporters cleanly. Reaching into private attributes is the only
       path — there is no public reset API.
    """
    from opentelemetry import _logs as otel_logs_api
    from opentelemetry import trace as otel_trace
    from opentelemetry.metrics import _internal as otel_metrics_internal

    from app.core import observability as obs

    def _reset() -> None:
        obs._TRACE_CONTEXT_WARNED = False
        obs._METRICS_EXPORTER_INSTALLED = False
        obs._LOG_EXPORTER_INSTALLED = False
        obs._TRACING_INSTALLED = False
        obs._RESOURCE_CACHE.clear()
        # OTel internals: clear the Once flag + the global slot so the
        # next set_tracer_provider / set_logger_provider call takes
        # effect instead of warning + no-op.
        otel_trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
        otel_trace._TRACER_PROVIDER = None  # type: ignore[attr-defined]
        otel_logs_api._internal._LOGGER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
        otel_logs_api._internal._LOGGER_PROVIDER = None  # type: ignore[attr-defined]
        # Metrics has a once-guard (``_METER_PROVIDER_SET_ONCE``) just
        # like traces + logs; the prior version of this fixture mis-
        # documented that it didn't. Clear both the guard and the
        # global slot so the next ``metrics.set_meter_provider`` call
        # takes effect rather than logging a warning and no-op'ing.
        otel_metrics_internal._METER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
        otel_metrics_internal._METER_PROVIDER = None  # type: ignore[attr-defined]

    _reset()
    yield
    _reset()


def _counter_value(
    reader: InMemoryMetricReader, name: str, attrs: dict[str, str]
) -> float:
    """Pull a single counter sample out of the captured metrics ledger.

    Returns 0.0 when the labelled series is absent — fresh proxy
    counters start unobserved. The reader exposes whatever the SDK has
    aggregated at this point; force_flush would only matter for
    push-based exporters (none here).
    """
    data = reader.get_metrics_data()
    if data is None:
        return 0.0
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name != name:
                    continue
                for dp in metric.data.data_points:
                    dp_attrs = dict(dp.attributes)
                    if all(dp_attrs.get(k) == v for k, v in attrs.items()):
                        return float(dp.value)
    return 0.0


# ---------------------------------------------------------------------------
# Conflict + FSM counters
# ---------------------------------------------------------------------------


MakeManager = Callable[..., User]
MakeHolder = Callable[..., User]


def _make_asset(
    db_session: Session,
    *,
    code: str = "AST-OBS-00001",
    name: str = "Observability Asset",
    status: AssetStatus = AssetStatus.IN_USE,
    holder: User | None = None,
) -> Asset:
    asset = Asset(
        asset_code=code,
        name=name,
        model="Dell Latitude 7440",
        category="computer",
        supplier="Dell",
        purchase_date=date(2025, 1, 1),
        purchase_amount=Decimal("1500.00"),
        location="Taipei HQ",
        department="IT",
        status=status,
        responsible_person_id=holder.id if holder is not None else None,
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def test_optimistic_conflict_counter_increments_on_409(
    client: TestClient,
    db_session: Session,
    make_user: MakeManager,
    auth_headers: Callable[[User], dict[str, str]],
    metric_reader: InMemoryMetricReader,
) -> None:
    """A 409 raised by the repair-request submit endpoint bumps the
    ``ams_optimistic_conflicts_total`` counter with the right attributes."""

    holder = make_user(role=UserRole.HOLDER)
    asset = _make_asset(db_session, holder=holder, status=AssetStatus.IN_USE)

    # Create an existing open repair request so the second submit collides
    # with the "one open request per asset" guard, which raises 409 with
    # `code=duplicate_request`.
    existing = RepairRequest(
        asset_id=asset.id,
        repair_id=_unique_repair_id(),
        requester_id=holder.id,
        status=RepairRequestStatus.PENDING_REVIEW,
        fault_description="prior open request",
    )
    db_session.add(existing)
    db_session.commit()

    before = _counter_value(
        metric_reader,
        "ams_optimistic_conflicts_total",
        {"code": "duplicate_request"},
    )

    # Submit a second repair request → endpoint raises 409 duplicate_request.
    response = client.post(
        "/api/v1/repair-requests",
        headers=auth_headers(holder),
        json={
            "asset_id": asset.id,
            "fault_description": "second request",
            "version": asset.version,
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "duplicate_request"

    after = _counter_value(
        metric_reader,
        "ams_optimistic_conflicts_total",
        {"code": "duplicate_request"},
    )
    assert after == before + 1, (before, after)


def test_fsm_transition_counter_increments_on_review_approval(
    client: TestClient,
    db_session: Session,
    make_user: MakeManager,
    auth_headers: Callable[[User], dict[str, str]],
    metric_reader: InMemoryMetricReader,
) -> None:
    """Approving a pending repair-request review bumps
    ``ams_fsm_transitions_total{state_from,state_to,asset_kind}``.

    The transition under test is PENDING_REVIEW → UNDER_REPAIR on the
    repair-request, asset-side PENDING_REPAIR → UNDER_REPAIR.
    """
    manager = make_user(role=UserRole.MANAGER)
    holder = make_user(role=UserRole.HOLDER)
    asset = _make_asset(
        db_session,
        holder=holder,
        status=AssetStatus.PENDING_REPAIR,
    )
    req = RepairRequest(
        asset_id=asset.id,
        repair_id=_unique_repair_id(),
        requester_id=holder.id,
        status=RepairRequestStatus.PENDING_REVIEW,
        fault_description="needs repair",
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    before = _counter_value(
        metric_reader,
        "ams_fsm_transitions_total",
        {"state_from": "PENDING_REVIEW", "state_to": "UNDER_REPAIR"},
    )

    response = client.post(
        f"/api/v1/repair-requests/{req.id}/approve",
        headers=auth_headers(manager),
        json={"version": req.version},
    )
    assert response.status_code == 200, response.text

    after = _counter_value(
        metric_reader,
        "ams_fsm_transitions_total",
        {"state_from": "PENDING_REVIEW", "state_to": "UNDER_REPAIR"},
    )
    assert after == before + 1, (before, after)


def test_fsm_transition_counter_submit_creates_new_request(
    client: TestClient,
    db_session: Session,
    make_user: MakeManager,
    auth_headers: Callable[[User], dict[str, str]],
    metric_reader: InMemoryMetricReader,
) -> None:
    """Submitting a new repair request bumps the counter with from=NONE.

    The submit transition is special: there is no prior state, so the
    ``from`` attribute is the sentinel literal ``"NONE"`` rather than an
    enum name. Pins that the source string stays in sync with the
    dashboard query in ``03-repair-journey.json``.
    """
    holder = make_user(role=UserRole.HOLDER)
    asset = _make_asset(db_session, holder=holder, status=AssetStatus.IN_USE)

    before = _counter_value(
        metric_reader,
        "ams_fsm_transitions_total",
        {"state_from": "NONE", "state_to": "PENDING_REVIEW"},
    )

    response = client.post(
        "/api/v1/repair-requests",
        headers=auth_headers(holder),
        json={
            "asset_id": asset.id,
            "fault_description": "new request",
            "version": asset.version,
        },
    )
    assert response.status_code in (200, 201), response.text

    after = _counter_value(
        metric_reader,
        "ams_fsm_transitions_total",
        {"state_from": "NONE", "state_to": "PENDING_REVIEW"},
    )
    assert after == before + 1, (before, after)


def test_fsm_transition_counter_review_rejection(
    client: TestClient,
    db_session: Session,
    make_user: MakeManager,
    auth_headers: Callable[[User], dict[str, str]],
    metric_reader: InMemoryMetricReader,
) -> None:
    """Rejecting a pending review bumps PENDING_REVIEW → REJECTED."""
    manager = make_user(role=UserRole.MANAGER)
    holder = make_user(role=UserRole.HOLDER)
    asset = _make_asset(
        db_session,
        holder=holder,
        status=AssetStatus.PENDING_REPAIR,
    )
    req = RepairRequest(
        asset_id=asset.id,
        repair_id=_unique_repair_id(),
        requester_id=holder.id,
        status=RepairRequestStatus.PENDING_REVIEW,
        fault_description="needs repair",
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    before = _counter_value(
        metric_reader,
        "ams_fsm_transitions_total",
        {"state_from": "PENDING_REVIEW", "state_to": "REJECTED"},
    )

    response = client.post(
        f"/api/v1/repair-requests/{req.id}/reject",
        headers=auth_headers(manager),
        json={"version": req.version, "rejection_reason": "out of scope"},
    )
    assert response.status_code == 200, response.text

    after = _counter_value(
        metric_reader,
        "ams_fsm_transitions_total",
        {"state_from": "PENDING_REVIEW", "state_to": "REJECTED"},
    )
    assert after == before + 1, (before, after)


def test_fsm_transition_counter_repair_completion(
    client: TestClient,
    db_session: Session,
    make_user: MakeManager,
    auth_headers: Callable[[User], dict[str, str]],
    metric_reader: InMemoryMetricReader,
) -> None:
    """Completing an in-repair request bumps UNDER_REPAIR → COMPLETED."""
    manager = make_user(role=UserRole.MANAGER)
    holder = make_user(role=UserRole.HOLDER)
    asset = _make_asset(
        db_session,
        holder=holder,
        status=AssetStatus.UNDER_REPAIR,
    )
    req = RepairRequest(
        asset_id=asset.id,
        repair_id=_unique_repair_id(),
        requester_id=holder.id,
        status=RepairRequestStatus.UNDER_REPAIR,
        fault_description="needs repair",
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    before = _counter_value(
        metric_reader,
        "ams_fsm_transitions_total",
        {"state_from": "UNDER_REPAIR", "state_to": "COMPLETED"},
    )

    response = client.post(
        f"/api/v1/repair-requests/{req.id}/complete",
        headers=auth_headers(manager),
        json={
            "version": req.version,
            "repair_date": str(date(2026, 5, 24)),
            "fault_content": "thermal paste worn",
            "repair_plan": "replaced thermal paste",
            "repair_cost": "150.00",
            "repair_vendor": "Vendor Co",
        },
    )
    assert response.status_code == 200, response.text

    after = _counter_value(
        metric_reader,
        "ams_fsm_transitions_total",
        {"state_from": "UNDER_REPAIR", "state_to": "COMPLETED"},
    )
    assert after == before + 1, (before, after)


# ---------------------------------------------------------------------------
# Structlog JSON renderer
# ---------------------------------------------------------------------------


def test_structlog_json_renderer_emits_trace_id_when_span_active() -> None:
    """When a tracing span is current, the structlog JSON renderer
    surfaces the active ``trace_id`` on log records."""

    from app.core.observability import _structlog_processor_trace_context

    class _FakeSpanCtx:
        is_valid = True
        trace_id = 0x0123456789ABCDEF0123456789ABCDEF
        span_id = 0xFEDCBA9876543210

    class _FakeSpan:
        def get_span_context(self) -> _FakeSpanCtx:  # noqa: D401 - protocol shape
            return _FakeSpanCtx()

    def _fake_get_current_span() -> _FakeSpan:
        return _FakeSpan()

    event = {"event": "hello"}
    out = _structlog_processor_trace_context(
        None, "info", event, _get_current_span=_fake_get_current_span
    )
    assert out["trace_id"] == f"{_FakeSpanCtx.trace_id:032x}"
    assert out["span_id"] == f"{_FakeSpanCtx.span_id:016x}"


def test_structlog_json_renderer_no_trace_id_when_no_span() -> None:
    """When no span is active, the processor leaves the event untouched."""

    from app.core.observability import _structlog_processor_trace_context

    class _InvalidSpanCtx:
        is_valid = False
        trace_id = 0
        span_id = 0

    class _NoOpSpan:
        def get_span_context(self) -> _InvalidSpanCtx:
            return _InvalidSpanCtx()

    out = _structlog_processor_trace_context(
        None, "info", {"event": "noop"}, _get_current_span=lambda: _NoOpSpan()
    )
    assert "trace_id" not in out
    assert "span_id" not in out


def test_structlog_processor_warns_only_once_on_repeated_get_span_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``_TRACE_CONTEXT_WARNED`` must silence subsequent failures.

    If the active-span lookup raises one of the narrowed exceptions
    (AttributeError, ImportError, RuntimeError), the processor logs
    a single warning naming the first failure and then stays silent
    for all subsequent calls in the same process. Without this guard
    a broken install would spam the request log on every log call.

    Drives ``_get_current_span`` to raise ``RuntimeError`` three
    times in a row and asserts exactly one "structlog trace_id
    stamping disabled" warning landed.
    """
    from app.core import observability as obs

    # The autouse fixture resets _TRACE_CONTEXT_WARNED to False
    # between tests; the assertion below relies on that.
    assert obs._TRACE_CONTEXT_WARNED is False

    def _broken_get_span() -> Any:
        raise RuntimeError("simulated SDK drift")

    with caplog.at_level(logging.WARNING, logger="app.core.observability"):
        for _ in range(3):
            out = obs._structlog_processor_trace_context(
                None,
                "info",
                {"event": "test"},
                _get_current_span=_broken_get_span,
            )
            assert "trace_id" not in out

    # Exactly one warning, even across three failing calls.
    matching = [
        rec for rec in caplog.records
        if "structlog trace_id stamping disabled" in rec.getMessage()
    ]
    assert len(matching) == 1, [rec.getMessage() for rec in matching]
    assert "simulated SDK drift" in matching[0].getMessage()
    # And the sentinel is now True so a future call stays silent.
    assert obs._TRACE_CONTEXT_WARNED is True


# ---------------------------------------------------------------------------
# setup_metrics_exporter / setup_log_exporter / maybe_setup_profiling
# ---------------------------------------------------------------------------


def _settings_with_otel(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    """Build a Settings with the OTLP flag flipped on against a dummy endpoint.

    The exporter calls never reach the network because the tests below
    either inspect the resulting provider's identity or intercept the
    underlying SDK calls before any send happens.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_ENDPOINT", "https://otlp-gateway.example/otlp")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Basic dGVzdA==")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    return Settings()  # type: ignore[call-arg]


def test_setup_metrics_passes_sanitize_and_excluded_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """setup_metrics MUST configure the FastAPIInstrumentor with sensitive-
    header sanitisation and health-probe URL exclusion.

    The bearer-token / cookie redaction is the defensive fix for the
    CRITICAL "Authorization header captured into spans" finding. The
    OTel FastAPI instrumentor's defaults today don't capture request
    headers, but operators could flip
    ``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST`` in the
    ECS task def for debugging — and once headers ARE captured, the
    sanitize regex list is what keeps live JWTs out of Grafana Cloud
    Tempo. Hard-coded via kwarg so an env-driven enable can't silently
    turn it off.

    The ``excluded_urls`` block is the span-cardinality fix: ALB
    health probes hit /health and /ready every few seconds and would
    otherwise dominate the trace volume budget with success spans of
    zero diagnostic value.
    """
    from unittest.mock import MagicMock, patch

    from fastapi import FastAPI

    from app.core import observability as obs

    settings = _settings_with_otel(monkeypatch)
    app = FastAPI()
    instrument_mock = MagicMock()
    with patch(
        "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app",
        instrument_mock,
    ):
        obs.setup_metrics(app, settings)

    instrument_mock.assert_called_once()
    kwargs = instrument_mock.call_args.kwargs
    excluded = kwargs.get("excluded_urls", "")
    # ALB liveness/readiness probes are excluded (cardinality fix) and
    # the frontend-failure beacon is excluded (circular-telemetry
    # avoidance: the beacon's own span would otherwise re-trigger the
    # beacon on export failure).
    for required_path in ("/health", "/ready", "/api/v1/observability/client-error"):
        assert required_path in excluded, (required_path, excluded)
    sanitize = kwargs.get("http_capture_headers_sanitize_fields")
    assert sanitize is not None, "sanitize regex list must be set"
    # All sensitive header families must be covered. Regex strings are
    # checked as substrings against this list so a future addition that
    # uses different anchors (e.g. ``^authorization$``) still satisfies
    # the contract.
    blob = " ".join(sanitize)
    for required in ("authorization", "cookie", "x-api-key", "proxy-authorization"):
        assert required in blob, (required, sanitize)


def test_setup_metrics_exporter_installs_working_meter_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """setup_metrics_exporter wires a real MeterProvider; module counters
    can ``.add(1, attributes=...)`` against it without raising.

    Patches the OTLP exporter so no background thread tries real DNS, and
    patches ``metrics.set_meter_provider`` to capture the provider built
    inside the function under test instead of hitting OTel's process-wide
    set-once guard.
    """
    from unittest.mock import MagicMock, patch

    from app.core import observability as obs

    settings = _settings_with_otel(monkeypatch)
    captured: dict[str, Any] = {}

    def _capture(provider: Any) -> None:
        captured["provider"] = provider
        # Shut the provider down immediately so its PeriodicExportingMetricReader
        # ticker thread exits before the test returns; otherwise it survives
        # past pytest's stdout-capture teardown and emits "I/O on closed file".
        provider.shutdown()

    # Swap the real OTLPMetricExporter for a mock that satisfies the SDK's
    # interface — the SDK calls ``.export`` and ``.shutdown`` only.
    fake_exporter = MagicMock()
    fake_exporter.export.return_value = None
    fake_exporter.shutdown.return_value = None
    fake_exporter._preferred_temporality = {}
    fake_exporter._preferred_aggregation = {}

    with (
        patch(
            "opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter",
            return_value=fake_exporter,
        ),
        patch.object(otel_metrics, "set_meter_provider", _capture),
    ):
        obs.setup_metrics_exporter(settings)

    assert "provider" in captured, "setup_metrics_exporter did not install a provider"
    assert isinstance(captured["provider"], MeterProvider), type(
        captured["provider"]
    ).__name__


def test_setup_metrics_exporter_is_noop_when_otel_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OTEL_ENABLED=false → setup_metrics_exporter does nothing.

    Guards the credential-less local boot. A failing import or stray
    background thread would surface here instead of in production.
    Patches ``set_meter_provider`` to a sentinel and asserts it was never
    called — robust against whatever the suite-wide proxy provider state
    happens to be when this test runs.
    """
    from unittest.mock import patch

    from app.core import observability as obs

    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    monkeypatch.delenv("OTEL_ENABLED", raising=False)
    settings = Settings()  # type: ignore[call-arg]

    called: list[Any] = []
    with patch.object(otel_metrics, "set_meter_provider", called.append):
        obs.setup_metrics_exporter(settings)
    assert called == [], called


def test_setup_log_exporter_bridges_trace_id_onto_log_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inside a span context, a stdlib log call must produce an OTel
    ``LogRecord`` whose ``trace_id`` matches the active span.

    Patches the OTLP exporter so no socket open happens; the SimpleLog
    processor on the captured InMemoryLogExporter is the only thing
    receiving records. If the structlog → OTel logs bridge order
    regresses (e.g. the OTel handler is added before the structlog root
    handler), this test fails because the captured record's
    ``trace_id`` is zero.
    """
    from opentelemetry import _logs as otel_logs_api
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import (
        InMemoryLogExporter,
        SimpleLogRecordProcessor,
    )
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from app.core import observability as obs

    settings = _settings_with_otel(monkeypatch)

    # Replace what setup_log_exporter would build with the SDK's in-memory
    # exporter, so no socket open is ever attempted.
    log_exp = InMemoryLogExporter()
    captured_provider: dict[str, Any] = {}

    def _fake_setup_log_exporter(s: Any) -> None:
        provider = LoggerProvider()
        provider.add_log_record_processor(SimpleLogRecordProcessor(log_exp))
        otel_logs_api.set_logger_provider(provider)
        captured_provider["p"] = provider
        handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
        logging.getLogger().addHandler(handler)

    # Install tracing so we have a real span context to read trace_id from.
    span_exp = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exp))
    otel_trace.set_tracer_provider(tracer_provider)
    tracer = otel_trace.get_tracer("test")

    saved_handlers = list(logging.getLogger().handlers)
    try:
        _fake_setup_log_exporter(settings)
        with tracer.start_as_current_span("span-under-test") as span:
            expected_trace_id = span.get_span_context().trace_id
            logging.getLogger("app.test.bridge").info("hello-from-span")

        captured_provider["p"].force_flush()
        records = log_exp.get_finished_logs()
        assert records, "no log records captured by the OTel bridge"
        matched = [
            r for r in records if r.log_record.body == "hello-from-span"
        ]
        assert matched, [r.log_record.body for r in records]
        assert matched[0].log_record.trace_id == expected_trace_id, (
            f"trace_id mismatch: record={matched[0].log_record.trace_id:032x} "
            f"expected={expected_trace_id:032x}"
        )
    finally:
        # Restore the root logger's handler list so the bridge handler
        # does not leak into subsequent tests in the suite.
        logging.getLogger().handlers = saved_handlers

    # Touch obs so the unused-import lint doesn't fire; the assertion
    # that matters is the trace_id one above.
    assert hasattr(obs, "setup_log_exporter")


def test_setup_log_exporter_is_noop_when_otel_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OTEL_ENABLED=false → setup_log_exporter adds no handler and does
    not touch the global LoggerProvider."""
    from app.core import observability as obs

    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    monkeypatch.delenv("OTEL_ENABLED", raising=False)
    settings = Settings()  # type: ignore[call-arg]

    handlers_before = list(logging.getLogger().handlers)
    obs.setup_log_exporter(settings)
    assert logging.getLogger().handlers == handlers_before


def test_maybe_setup_profiling_calls_pyroscope_configure_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Locked-decision-5 reversal: Pyroscope is enabled in production.

    Previously ``maybe_setup_profiling`` was documented as a no-op in
    prod because the W6 plan assumed gunicorn would fork after
    pyroscope.configure. The prod migration plan reverses this: with
    ``WEB_CONCURRENCY=1`` and no ``--preload`` the sampling thread
    starts inside the worker post-fork. This test asserts the call
    actually happens — a future refactor that re-adds an "environment
    == production → skip" branch will fail loud here.
    """
    import sys
    import types
    from unittest.mock import MagicMock

    from app.core import observability as obs

    fake_pyroscope = types.ModuleType("pyroscope")
    fake_pyroscope.configure = MagicMock()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyroscope", fake_pyroscope)

    settings = _settings_with_otel(
        monkeypatch,
        PYROSCOPE_ENABLED="true",
        PYROSCOPE_SERVER="https://profiles.example",
        PYROSCOPE_AUTH_TOKEN="tok-xyz",
        PYROSCOPE_BASIC_AUTH_USERNAME="123456",
        ENVIRONMENT="production",
    )

    obs.maybe_setup_profiling(settings)

    fake_pyroscope.configure.assert_called_once()  # type: ignore[attr-defined]
    kwargs = fake_pyroscope.configure.call_args.kwargs  # type: ignore[attr-defined]
    assert kwargs["application_name"].startswith("ams-backend.")
    assert kwargs["server_address"] == "https://profiles.example"
    assert kwargs["basic_auth_username"] == "123456"
    assert kwargs["auth_token"] == "tok-xyz"


# ---------------------------------------------------------------------------
# Settings observability fields
# ---------------------------------------------------------------------------


def test_settings_observability_fields_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """New observability fields exist with safe defaults.

    Defaults must be off so a stale ECS task without the Phase 3 env
    overrides keeps booting; an operator opts in by setting
    ``OTEL_ENABLED=true``.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    # Wipe any inherited values from the test process so we observe defaults.
    for var in (
        "OTEL_ENABLED",
        "OTEL_ENDPOINT",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "PYROSCOPE_ENABLED",
        "PYROSCOPE_SERVER",
        "PYROSCOPE_AUTH_TOKEN",
        "PYROSCOPE_BASIC_AUTH_USERNAME",
        "ENVIRONMENT",
        "REPLICA_ID",
        "LOG_FORMAT",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings()  # type: ignore[call-arg]
    assert settings.otel_enabled is False
    # Endpoint defaults are empty so the source never ships a clear-text
    # URL literal; operators set the value when they flip the flag on.
    assert settings.otel_endpoint == ""
    assert settings.otel_exporter_otlp_headers.get_secret_value() == ""
    assert settings.pyroscope_enabled is False
    assert settings.pyroscope_server == ""
    assert settings.pyroscope_auth_token.get_secret_value() == ""
    assert settings.pyroscope_basic_auth_username == ""
    assert settings.environment == "local"
    # Default replica id is hostname-derived; just confirm it's a non-empty str.
    assert isinstance(settings.replica_id, str) and settings.replica_id
    assert settings.log_format == "json"


@pytest.mark.parametrize(
    ("flag_env", "url_env"),
    [
        ("OTEL_ENABLED", "OTEL_ENDPOINT"),
        ("PYROSCOPE_ENABLED", "PYROSCOPE_SERVER"),
    ],
)
def test_settings_observability_flag_requires_url(
    monkeypatch: pytest.MonkeyPatch, flag_env: str, url_env: str
) -> None:
    """Flipping a feature flag on without setting its URL must fail loud."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    monkeypatch.delenv(url_env, raising=False)
    monkeypatch.setenv(flag_env, "true")

    with pytest.raises(ValueError, match=url_env):
        Settings()  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("flag_env", "url_env"),
    [
        ("OTEL_ENABLED", "OTEL_ENDPOINT"),
        ("PYROSCOPE_ENABLED", "PYROSCOPE_SERVER"),
    ],
)
def test_settings_observability_endpoints_must_be_https(
    monkeypatch: pytest.MonkeyPatch, flag_env: str, url_env: str
) -> None:
    """An ``http://`` endpoint must be rejected at boot.

    Plaintext OTLP would leak the GC API key carried in
    ``OTEL_EXPORTER_OTLP_HEADERS``; the only legitimate GC OTLP /
    Pyroscope targets are HTTPS.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    monkeypatch.setenv(flag_env, "true")
    monkeypatch.setenv(url_env, "http://attacker.example/otlp")
    # Needed for OTLP path only — Pyroscope-only test still tolerates it.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Basic dGVzdA==")

    with pytest.raises(ValueError, match="https://"):
        Settings()  # type: ignore[call-arg]


def test_settings_otel_enabled_in_production_requires_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OTLP without auth headers in a non-local env must fail loud.

    ``OTEL_ENABLED=true`` + ``ENVIRONMENT!=local`` + empty
    ``OTEL_EXPORTER_OTLP_HEADERS`` means the exporter ships every
    span/metric/log unauthenticated; GC silently 401s and observability
    degrades to nothing with no application-visible error. We refuse to
    boot in that shape so the misconfiguration surfaces immediately.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_ENDPOINT", "https://otlp-gateway.example/otlp")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_HEADERS", raising=False)

    with pytest.raises(ValueError, match="OTEL_EXPORTER_OTLP_HEADERS"):
        Settings()  # type: ignore[call-arg]


def test_settings_otel_enabled_locally_does_not_require_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The headers check is gated on non-local environments.

    Local-with-otel-on (e.g. a developer testing the exporter wire against
    a self-hosted Tempo) must remain bootable without forcing a fake header
    just to satisfy the validator.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_ENDPOINT", "https://otlp-gateway.example/otlp")
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_HEADERS", raising=False)

    # Must not raise.
    Settings()  # type: ignore[call-arg]


def test_parse_otlp_headers_handles_comma_separated_pairs() -> None:
    """Canonical OTLP header string parses into a dict.

    Pins the M3 fix: the OTLP exporter SDK accepts both raw string
    and dict shapes across the pinned ``>=1.27,<2.0`` SDK range, but
    the dict shape is unambiguous regardless of minor version flip.
    """
    from app.core.observability import _parse_otlp_headers

    parsed = _parse_otlp_headers("Authorization=Basic dGVzdA==,X-Scope-OrgID=42")
    assert parsed == {"Authorization": "Basic dGVzdA==", "X-Scope-OrgID": "42"}


def test_parse_otlp_headers_returns_none_for_empty() -> None:
    """Empty / whitespace input returns None so the SDK skips headers."""
    from app.core.observability import _parse_otlp_headers

    assert _parse_otlp_headers("") is None
    assert _parse_otlp_headers("   ") is None


def test_parse_otlp_headers_skips_malformed_pair_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A malformed pair (no '=') is skipped + warned, not raised.

    Operators get the same fail-open semantics they had before (where
    a bad pair would have been forwarded to the SDK and silently
    mis-tokenized), with the addition of a structured warning so the
    misconfig is visible in Loki.
    """
    from app.core.observability import _parse_otlp_headers

    with caplog.at_level(logging.WARNING, logger="app.core.observability"):
        parsed = _parse_otlp_headers("Authorization=Basic dGVzdA==,not-a-pair,X=Y")
    assert parsed == {"Authorization": "Basic dGVzdA==", "X": "Y"}
    assert any("malformed pair" in rec.message for rec in caplog.records), [
        rec.message for rec in caplog.records
    ]


def test_parse_otlp_headers_does_not_log_raw_pair_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """M2 contract: the malformed-pair value MUST NOT land in any log record.

    A typo'd ``OTEL_EXPORTER_OTLP_HEADERS`` where the key is omitted
    (e.g. ``"Bearer mytoken"`` instead of ``"Authorization=Bearer mytoken"``)
    is a no-``=`` pair whose entire VALUE is a credential. The previous
    ``%r`` formatter landed the literal token in Loki / CloudWatch. The
    M2 fix replaces it with offset + length only — locked here so a
    future refactor reintroducing the raw value would fail this test
    rather than silently leaking the secret.
    """
    from app.core.observability import _parse_otlp_headers

    sentinel_credential = "BearerSentinelOnly_a1b2c3d4e5f6"
    with caplog.at_level(logging.WARNING, logger="app.core.observability"):
        _parse_otlp_headers(f"Authorization=ok,{sentinel_credential},X=Y")
    for rec in caplog.records:
        assert sentinel_credential not in rec.message, rec.message
        assert sentinel_credential not in str(getattr(rec, "args", ())), rec.args


def test_parse_otlp_headers_trims_whitespace() -> None:
    """Whitespace around tokens is trimmed (matches OTel spec)."""
    from app.core.observability import _parse_otlp_headers

    parsed = _parse_otlp_headers("  Authorization = Basic dGVzdA== ,  X = Y ")
    assert parsed == {"Authorization": "Basic dGVzdA==", "X": "Y"}


def test_build_resource_cache_evicts_oldest_at_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_build_resource``'s cache is bounded — overflow evicts the oldest.

    The cache exists so the OTel SDK's host/process auto-detection
    doesn't re-run on every ``setup_*_exporter`` call (production
    invokes three setup_* calls in sequence on the same Resource
    tuple). Without an explicit bound, a long-running test session
    that constructs many distinct ``Settings`` shapes — or a future
    feature that recomputes the Resource per-request — would grow
    the cache unboundedly. Lock the eviction contract.
    """
    from app.core import observability as obs

    obs._RESOURCE_CACHE.clear()
    cap = obs._RESOURCE_CACHE_MAX

    # Fill the cache to capacity using a different ``replica_id`` per
    # call. ``settings.replica_id`` comes from HOSTNAME env / hostname()
    # — monkeypatching the env var per iteration drives a fresh key.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")

    first_key = None
    for replica in range(cap):
        monkeypatch.setenv("HOSTNAME", f"replica-{replica}")
        settings = Settings()  # type: ignore[call-arg]
        obs._build_resource(settings)
        if replica == 0:
            first_key = next(iter(obs._RESOURCE_CACHE))

    assert len(obs._RESOURCE_CACHE) == cap, (
        f"cache should be at capacity ({cap}); got {len(obs._RESOURCE_CACHE)}"
    )
    assert first_key in obs._RESOURCE_CACHE

    # One more insertion should evict the oldest entry, not the newest.
    monkeypatch.setenv("HOSTNAME", "replica-overflow")
    settings_overflow = Settings()  # type: ignore[call-arg]
    obs._build_resource(settings_overflow)

    assert len(obs._RESOURCE_CACHE) == cap, (
        f"cache size must stay at capacity after overflow; got {len(obs._RESOURCE_CACHE)}"
    )
    assert first_key not in obs._RESOURCE_CACHE, (
        f"oldest key {first_key} should have been evicted; cache: {list(obs._RESOURCE_CACHE)}"
    )


@pytest.mark.parametrize(
    "missing_env",
    ["PYROSCOPE_AUTH_TOKEN", "PYROSCOPE_BASIC_AUTH_USERNAME"],
)
def test_settings_pyroscope_enabled_in_production_requires_auth(
    monkeypatch: pytest.MonkeyPatch, missing_env: str
) -> None:
    """Pyroscope without either basic-auth half in non-local env must fail loud.

    The OTLP startup probe (verify_observability_exports) does not cover
    Pyroscope — pyroscope-io has no synchronous flush surface — so a
    missing PYROSCOPE_AUTH_TOKEN or PYROSCOPE_BASIC_AUTH_USERNAME would
    silently 401 against GC and leave profiling dark in production. Refuse
    to boot in that shape; same posture as the OTLP headers validator.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    monkeypatch.setenv("PYROSCOPE_ENABLED", "true")
    monkeypatch.setenv("PYROSCOPE_SERVER", "https://profiles-prod.grafana.net")
    monkeypatch.setenv("PYROSCOPE_AUTH_TOKEN", "tok-xyz")
    monkeypatch.setenv("PYROSCOPE_BASIC_AUTH_USERNAME", "123456")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv(missing_env, raising=False)

    with pytest.raises(ValueError, match="PYROSCOPE_AUTH_TOKEN"):
        Settings()  # type: ignore[call-arg]


def test_settings_pyroscope_enabled_locally_does_not_require_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local Pyroscope-on must boot without credentials.

    A developer pointing at a self-hosted Pyroscope server with no auth
    (or whose dev setup uses cookie-based auth) must not be blocked by
    the production-gated validator.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    monkeypatch.setenv("PYROSCOPE_ENABLED", "true")
    monkeypatch.setenv("PYROSCOPE_SERVER", "https://profiles-prod.grafana.net")
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("PYROSCOPE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("PYROSCOPE_BASIC_AUTH_USERNAME", raising=False)

    # Must not raise.
    Settings()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# verify_observability_exports startup probe
# ---------------------------------------------------------------------------


def test_verify_observability_exports_noop_when_otel_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No flush attempted when OTEL_ENABLED is false (dev default)."""
    from app.core import observability as obs

    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    monkeypatch.delenv("OTEL_ENABLED", raising=False)
    settings = Settings()  # type: ignore[call-arg]

    # Must not raise and must not touch provider state.
    obs.verify_observability_exports(settings)


def test_verify_observability_exports_noop_in_local_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe is gated to non-local environments.

    A developer running with OTEL_ENABLED=true against a self-hosted
    collector must not be blocked at boot if the collector is offline.
    """
    from app.core import observability as obs

    settings = _settings_with_otel(monkeypatch, ENVIRONMENT="local")
    obs.verify_observability_exports(settings)


def _patch_all_providers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    metrics_flush: bool = True,
    traces_flush: bool = True,
    logs_flush: bool = True,
) -> dict[str, Any]:
    """Install fake real-shaped providers + flip the install flags True.

    ``verify_observability_exports`` now refuses to proceed unless every
    signal's ``_*_INSTALLED`` flag is True (the regression fix for the
    silent-export-skip class). Test arrangements that previously relied
    on the global no-op providers being silently skipped must now declare
    the provider state explicitly.
    """
    from unittest.mock import MagicMock

    from app.core import observability as obs

    obs._METRICS_EXPORTER_INSTALLED = True
    obs._TRACING_INSTALLED = True
    obs._LOG_EXPORTER_INSTALLED = True

    meter_mock = MagicMock()
    meter_mock.force_flush = MagicMock(return_value=metrics_flush)
    tracer_mock = MagicMock()
    tracer_mock.force_flush = MagicMock(return_value=traces_flush)
    logger_mock = MagicMock()
    logger_mock.force_flush = MagicMock(return_value=logs_flush)

    monkeypatch.setattr(
        "opentelemetry.metrics.get_meter_provider", lambda: meter_mock
    )
    monkeypatch.setattr(
        "opentelemetry.trace.get_tracer_provider", lambda: tracer_mock
    )
    monkeypatch.setattr(
        "opentelemetry._logs.get_logger_provider", lambda: logger_mock
    )
    return {"metrics": meter_mock, "traces": tracer_mock, "logs": logger_mock}


def test_verify_observability_exports_raises_on_flush_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A False return from any provider's force_flush surfaces as RuntimeError.

    Simulates the wrong-API-key / unreachable-OTLP-gateway scenario by
    patching the global meter provider to return False from force_flush.
    The probe must raise so the ECS task crashes before being marked
    healthy by the ALB.
    """
    from app.core import observability as obs

    settings = _settings_with_otel(monkeypatch, ENVIRONMENT="production")
    _patch_all_providers(monkeypatch, metrics_flush=False)

    with pytest.raises(RuntimeError, match="metrics-flush"):
        obs.verify_observability_exports(settings)


def test_app_main_import_crashes_when_verify_observability_exports_raises(
    tmp_path: Path,
) -> None:
    """Boot-crash contract: ``import app.main`` MUST propagate the RuntimeError.

    ``verify_observability_exports`` is called at the module-import
    top level of ``app.main`` with no surrounding try/except. The
    silent-failure regression risk: a future refactor that wrapped
    the call in ``try/except`` (or moved it behind a feature flag
    that defaults off) would silently re-open the export-failure
    gap — a wrong OTLP API key in prod would let the container boot
    and pass the ALB health check while every trace / metric / log
    was being dropped on the floor.

    No existing test pinned the "no try-wrap; the container DOES
    crash" contract. This one does it via subprocess isolation: the
    test process already has ``app.main`` imported (conftest pulled
    it in), so an in-process ``importlib.reload`` would entangle
    fixtures + the test's own global state. A clean subprocess
    booted with the right env vars + a monkeypatch site for the
    verify probe is the cheapest honest way to verify the
    fail-loud contract end-to-end.
    """
    import subprocess
    import sys
    import textwrap

    # Build a tiny sitecustomize.py that monkeypatches the verify probe
    # to raise BEFORE app.main's module-level call runs. Drop it into
    # tmp_path and prepend tmp_path to PYTHONPATH so it loads first.
    sitecustomize = tmp_path / "sitecustomize.py"
    sitecustomize.write_text(
        textwrap.dedent(
            """
            # Force verify_observability_exports to raise so we can
            # observe whether app.main propagates or swallows.
            import app.core.observability as _obs

            def _explode(_settings):
                raise RuntimeError(
                    "synthetic failure: simulated OTLP wrong-API-key"
                )

            _obs.verify_observability_exports = _explode
            """
        )
    )

    # Repo root for PYTHONPATH so ``import app.main`` resolves the
    # backend package — anchored on this test file's location so the
    # test runs regardless of pytest's CWD.
    backend_root = Path(__file__).resolve().parent.parent

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{tmp_path}{os.pathsep}{backend_root}"
    # ``app.main`` reads these at import; pass minimal valid values so
    # nothing else fails before our synthetic verify probe runs.
    env.setdefault("DATABASE_URL", "sqlite:///:memory:")
    env.setdefault("JWT_SECRET", "x")
    env.setdefault("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    env.setdefault("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    env.setdefault("RATE_LIMIT_ENABLED", "false")  # skip the worker-count guard

    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    # The contract: import MUST fail, returncode MUST be non-zero,
    # and the synthetic RuntimeError message MUST appear in stderr
    # so an operator reading container logs can identify the cause.
    assert result.returncode != 0, (
        f"app.main imported cleanly even though verify_observability_exports "
        f"raised — the boot-crash contract is broken. stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert "synthetic failure" in result.stderr, result.stderr
    assert "RuntimeError" in result.stderr, result.stderr


def test_verify_observability_exports_passes_on_successful_flush(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All providers returning True from force_flush is the happy path."""
    from app.core import observability as obs

    settings = _settings_with_otel(monkeypatch, ENVIRONMENT="production")
    fakes = _patch_all_providers(monkeypatch)

    obs.verify_observability_exports(settings)
    # All three signals flushed; mocks were each invoked exactly once with
    # the 5 s timeout. A regression that skipped a signal's flush silently
    # would fail one of these assertions.
    fakes["metrics"].force_flush.assert_called_once_with(5_000)
    fakes["traces"].force_flush.assert_called_once_with(5_000)
    fakes["logs"].force_flush.assert_called_once_with(5_000)


@pytest.mark.parametrize(
    ("missing_flag", "expected_signal"),
    [
        ("_METRICS_EXPORTER_INSTALLED", "metrics"),
        ("_TRACING_INSTALLED", "traces"),
        ("_LOG_EXPORTER_INSTALLED", "logs"),
    ],
)
def test_verify_observability_exports_fails_when_install_flag_false(
    monkeypatch: pytest.MonkeyPatch,
    missing_flag: str,
    expected_signal: str,
) -> None:
    """The probe refuses to proceed when any installer never finished.

    Locks the CRITICAL fix for the silent-logs-skip regression. The pre-
    fix implementation used ``getattr(provider, "force_flush", None)`` +
    ``callable`` guards, so a signal whose ``setup_*_exporter`` raised
    silently fell through to ``force_flush returned True trivially`` —
    the probe gave false confidence against an exporter that never ran.
    """
    from app.core import observability as obs

    settings = _settings_with_otel(monkeypatch, ENVIRONMENT="production")
    _patch_all_providers(monkeypatch)
    # Flip exactly one install flag back to False — the probe must
    # surface that signal in the RuntimeError before reaching flush.
    setattr(obs, missing_flag, False)

    with pytest.raises(RuntimeError, match=f"not installed for: {expected_signal}"):
        obs.verify_observability_exports(settings)
def test_proxy_counter_increments_after_late_provider_install() -> None:
    """Counters created at import time must record into a MeterProvider
    installed AFTER the create_counter call.
    Load-bearing invariant: FSM_TRANSITIONS and OPTIMISTIC_CONFLICTS are
    instantiated at module import time, well before ``setup_metrics_exporter``
    runs in ``app/main.py``. OTel's ProxyCounter is supposed to rebind on
    the next set_meter_provider call. The fixture used by other tests in
    this file rebinds BEFORE incrementing — so it doesn't directly prove
    the cross-swap. This test does:
    1. Increment FSM_TRANSITIONS while the proxy still points at no-op.
    2. Install a real InMemoryMetricReader-backed MeterProvider.
    3. Increment again with a different attribute set.
    4. Assert pre-install increment is invisible to the new reader
       (no-op silently dropped); post-install increment is recorded.
    A regression that moved counter creation into ``setup_metrics_exporter``
    or that broke the proxy rebind path would fail step 4.
    """
    from opentelemetry.metrics._internal import _PROXY_METER_PROVIDER

    from app.core import observability as obs
    pre_attrs = {"state_from": "PROBE_PRE", "state_to": "PROBE_PRE", "asset_kind": "asset"}
    post_attrs = {
        "state_from": "PENDING_REVIEW",
        "state_to": "UNDER_REPAIR",
        "asset_kind": "repair_request",
    }
    obs.FSM_TRANSITIONS.add(1, attributes=pre_attrs)
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    _PROXY_METER_PROVIDER.on_set_meter_provider(provider)
    try:
        obs.FSM_TRANSITIONS.add(1, attributes=post_attrs)
        pre_value = _counter_value(
            reader, "ams_fsm_transitions_total", pre_attrs
        )
        post_value = _counter_value(
            reader, "ams_fsm_transitions_total", post_attrs
        )
        assert pre_value == 0.0, (
            "pre-install increment must not appear in the post-install reader"
        )
        assert post_value == 1.0, (
            f"post-install increment must be recorded: got {post_value}"
        )
    finally:
        _PROXY_METER_PROVIDER.on_set_meter_provider(otel_metrics.NoOpMeterProvider())
def test_setup_log_exporter_bridges_trace_id_via_structlog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A structlog log call inside a span must reach the OTel LogRecord
    with the active trace_id stamped on it.
    The existing ``test_setup_log_exporter_bridges_trace_id_onto_log_records``
    drives the bridge via ``logging.getLogger(...).info(...)`` — that proves
    ``stdlib -> OTel``. This test drives it via ``structlog.get_logger(...)
    .info(...)``, which exercises the full chain ``structlog ->
    ProcessorFormatter -> stdlib -> OTel LoggingHandler`` that's actually
    in use everywhere in the app. A regression in any of those seams (e.g.
    structlog's processor chain dropping the trace context, or the
    ProcessorFormatter swallowing the underlying LogRecord) fails here but
    not in the stdlib-only test.
    """
    import structlog
    from opentelemetry import _logs as otel_logs_api
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import (
        InMemoryLogExporter,
        SimpleLogRecordProcessor,
    )
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from app.core import observability as obs
    settings = _settings_with_otel(monkeypatch)
    obs.setup_logging(settings)
    log_exp = InMemoryLogExporter()
    logger_provider = LoggerProvider()
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exp))
    otel_logs_api.set_logger_provider(logger_provider)
    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    span_exp = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exp))
    otel_trace.set_tracer_provider(tracer_provider)
    tracer = otel_trace.get_tracer("test")
    saved_handlers = list(logging.getLogger().handlers)
    logging.getLogger().addHandler(handler)
    try:
        with tracer.start_as_current_span("structlog-span") as span:
            expected_trace_id = span.get_span_context().trace_id
            structlog.get_logger("app.test.structlog.bridge").info(
                "hello-from-structlog"
            )
        logger_provider.force_flush()
        records = log_exp.get_finished_logs()
        matched = [
            r
            for r in records
            if r.log_record.body is not None
            and "hello-from-structlog" in str(r.log_record.body)
        ]
        assert matched, (
            "no log records flowed structlog -> OTel: "
            f"captured bodies={[str(r.log_record.body) for r in records]}"
        )
        assert matched[0].log_record.trace_id == expected_trace_id, (
            f"trace_id mismatch: record={matched[0].log_record.trace_id:032x} "
            f"expected={expected_trace_id:032x}"
        )
    finally:
        logging.getLogger().handlers = saved_handlers
def test_maybe_setup_profiling_is_noop_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PYROSCOPE_ENABLED=false (the default) -> no import, no configure call.
    The Pyroscope-in-prod reversal is one half of the contract; the other
    half is that the flag still cleanly turns it off. Without this test,
    a regression that removed the early return at the top of
    ``maybe_setup_profiling`` would pass CI silently.
    """
    import sys
    import types
    from unittest.mock import MagicMock

    from app.core import observability as obs
    fake_pyroscope = types.ModuleType("pyroscope")
    fake_pyroscope.configure = MagicMock()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyroscope", fake_pyroscope)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    monkeypatch.delenv("PYROSCOPE_ENABLED", raising=False)
    settings = Settings()  # type: ignore[call-arg]
    obs.maybe_setup_profiling(settings)
    fake_pyroscope.configure.assert_not_called()  # type: ignore[attr-defined]
def test_maybe_setup_profiling_logs_warning_on_missing_pyroscope(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    metric_reader: InMemoryMetricReader,
) -> None:
    """PYROSCOPE_ENABLED=true + pyroscope-io not installed -> warn, counter ticks, do not crash.

    The dev image deliberately omits the ``prod`` extra to keep the local
    venv slim. A developer flipping PYROSCOPE_ENABLED=true without
    installing pyroscope-io must still boot, with a clear warning in the
    logs AND a counter increment so operators can alert on
    ``rate(ams_profiling_init_failures_total[5m]) > 0`` for the
    missing-wheel-in-prod regression.
    """
    import sys

    from app.core import observability as obs
    monkeypatch.setitem(sys.modules, "pyroscope", None)
    settings = _settings_with_otel(
        monkeypatch,
        PYROSCOPE_ENABLED="true",
        PYROSCOPE_SERVER="https://profiles.example",
        PYROSCOPE_AUTH_TOKEN="tok-xyz",
        PYROSCOPE_BASIC_AUTH_USERNAME="123456",
        ENVIRONMENT="production",
    )
    with caplog.at_level(logging.WARNING, logger="app.core.observability"):
        obs.maybe_setup_profiling(settings)
    assert any(
        "pyroscope-io is unavailable" in rec.message for rec in caplog.records
    ), [rec.message for rec in caplog.records]
    assert _counter_value(
        metric_reader,
        "ams_profiling_init_failures_total",
        {"reason": "missing_dependency"},
    ) == 1.0


def test_maybe_setup_profiling_handles_broken_wheel_oserror(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    metric_reader: InMemoryMetricReader,
) -> None:
    """M6 contract: pyroscope-io import raising OSError -> warn + counter, never crash.

    ``pyroscope-io`` wraps a Rust client linked against libssl. On
    Alpine / musl-based images a broken wheel can be present but
    raise ``OSError: cannot load library`` at import time. Pre-M6
    this propagated out of ``maybe_setup_profiling`` and crashed
    boot — contradicting the docstring promise that "a profiling
    misconfig never crashes the request-serving path." Post-M6 the
    catch widens to ``(ImportError, OSError)`` so a broken wheel is
    operationally identical to a missing wheel (both want the prod
    extra reinstalled).
    """
    import builtins

    from app.core import observability as obs

    real_import = builtins.__import__

    def _fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "pyroscope":
            raise OSError("cannot load library libssl.so.1.1")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    settings = _settings_with_otel(
        monkeypatch,
        PYROSCOPE_ENABLED="true",
        PYROSCOPE_SERVER="https://profiles.example",
        PYROSCOPE_AUTH_TOKEN="tok-xyz",
        PYROSCOPE_BASIC_AUTH_USERNAME="123456",
        ENVIRONMENT="production",
    )
    with caplog.at_level(logging.WARNING, logger="app.core.observability"):
        # Must NOT raise — broken wheel is operationally same as missing wheel.
        obs.maybe_setup_profiling(settings)
    matched = [
        rec for rec in caplog.records
        if "pyroscope-io is unavailable" in rec.message
    ]
    assert matched, [rec.message for rec in caplog.records]
    # The exception type AND message should land in the WARN so the
    # operator can distinguish missing-wheel from broken-wheel from
    # the log alone.
    assert "OSError" in matched[0].message, matched[0].message
    assert "libssl" in matched[0].message, matched[0].message
    # Counter ticks under the same `missing_dependency` reason — same
    # remediation (reinstall the prod extra), same alert rule.
    assert _counter_value(
        metric_reader,
        "ams_profiling_init_failures_total",
        {"reason": "missing_dependency"},
    ) == 1.0
def test_maybe_setup_profiling_logs_warning_on_configure_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    metric_reader: InMemoryMetricReader,
) -> None:
    """pyroscope.configure raising must be logged + counted, not propagated.

    Pyroscope misconfig (bad token, unreachable profiles endpoint, dep
    version mismatch) is not worth crashing the app over. The fix wraps
    configure() in narrow try/except for ``(RuntimeError, OSError,
    ValueError)``; this test holds the line and asserts the counter
    increments under ``reason=configure_error`` for the alert rule.
    """
    import sys
    import types
    from unittest.mock import MagicMock

    from app.core import observability as obs
    fake_pyroscope = types.ModuleType("pyroscope")
    fake_pyroscope.configure = MagicMock(  # type: ignore[attr-defined]
        side_effect=RuntimeError("auth: invalid token")
    )
    monkeypatch.setitem(sys.modules, "pyroscope", fake_pyroscope)
    settings = _settings_with_otel(
        monkeypatch,
        PYROSCOPE_ENABLED="true",
        PYROSCOPE_SERVER="https://profiles.example",
        PYROSCOPE_AUTH_TOKEN="tok-bad",
        PYROSCOPE_BASIC_AUTH_USERNAME="123456",
        ENVIRONMENT="production",
    )
    with caplog.at_level(logging.WARNING, logger="app.core.observability"):
        obs.maybe_setup_profiling(settings)
    assert any(
        "Pyroscope configure failed" in rec.message for rec in caplog.records
    ), [rec.message for rec in caplog.records]
    assert _counter_value(
        metric_reader,
        "ams_profiling_init_failures_total",
        {"reason": "configure_error"},
    ) == 1.0


def test_maybe_setup_profiling_propagates_programmer_typeerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A TypeError out of pyroscope.configure surfaces, not silently swallowed.

    The narrow except clause deliberately omits TypeError because
    that shape implies the calling code passed the wrong kwargs —
    a programmer bug that should crash the test suite (or boot),
    not be hidden behind a warning + counter.
    """
    import sys
    import types
    from unittest.mock import MagicMock

    from app.core import observability as obs
    fake_pyroscope = types.ModuleType("pyroscope")
    fake_pyroscope.configure = MagicMock(  # type: ignore[attr-defined]
        side_effect=TypeError("unexpected keyword argument 'foo'")
    )
    monkeypatch.setitem(sys.modules, "pyroscope", fake_pyroscope)
    settings = _settings_with_otel(
        monkeypatch,
        PYROSCOPE_ENABLED="true",
        PYROSCOPE_SERVER="https://profiles.example",
        PYROSCOPE_AUTH_TOKEN="tok-xyz",
        PYROSCOPE_BASIC_AUTH_USERNAME="123456",
        ENVIRONMENT="production",
    )
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        obs.maybe_setup_profiling(settings)
def test_verify_observability_exports_emits_synthetic_signals_before_flush(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The probe emits one synthetic span/metric/log BEFORE flushing.
    force_flush on an empty buffer returns True trivially. Without a
    synthetic emit, the probe gives false confidence: a completely
    wrong API key would pass the probe and only fail on the first
    real request's export attempt. The fix emits a synthetic counter
    increment, span, and log line tagged with ``ams.probe=startup`` so
    the BatchProcessors and PeriodicExportingMetricReader actually push
    something during force_flush.
    This test asserts both synthetic artefacts land where they should.
    """
    from unittest.mock import MagicMock

    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from app.core import observability as obs
    settings = _settings_with_otel(monkeypatch, ENVIRONMENT="production")
    reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[reader])
    # Use the PUBLIC API for installing the meter provider. The autouse
    # fixture ``_reset_observability_module_state`` clears
    # ``_METER_PROVIDER_SET_ONCE`` per test, so this call takes effect
    # rather than warning + no-op'ing. The prior version of this test
    # reached into the ``_METER_PROVIDER`` private slot directly — that
    # attribute has churned across OTel ``>=1.27,<2.0`` minors, so
    # going through ``set_meter_provider`` is rot-resistant.
    otel_metrics.set_meter_provider(meter_provider)
    span_exp = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exp))
    otel_trace.set_tracer_provider(tracer_provider)
    # The strict-install-flag check refuses to proceed without all three
    # signals' flags set. The test exercises the synthetic-emit path
    # under real metric + trace providers; log provider is mocked so the
    # log flush also clears.
    obs._METRICS_EXPORTER_INSTALLED = True
    obs._TRACING_INSTALLED = True
    obs._LOG_EXPORTER_INSTALLED = True
    log_provider_mock = MagicMock()
    log_provider_mock.force_flush = MagicMock(return_value=True)
    monkeypatch.setattr(
        "opentelemetry._logs.get_logger_provider", lambda: log_provider_mock
    )
    try:
        obs.verify_observability_exports(settings)
    finally:
        # Autouse ``_reset_observability_module_state`` will fully tear
        # the provider down between tests; this in-test pass-through
        # reset just protects the assertion block below in case OTel
        # adds eager re-bind semantics in a future minor.
        pass
    probe_value = _counter_value(
        reader,
        "ams_observability_probe_total",
        {"ams.probe": "startup"},
    )
    assert probe_value == 1.0, (
        f"synthetic counter increment missing: got {probe_value}"
    )
    spans = span_exp.get_finished_spans()
    probe_spans = [s for s in spans if s.name == "observability_probe"]
    assert probe_spans, (
        f"synthetic span not recorded; saw {[s.name for s in spans]}"
    )
    attrs = probe_spans[0].attributes or {}
    assert attrs.get("ams.probe") == "startup", attrs
def test_verify_observability_exports_surfaces_synthetic_emit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken instrument during the synthetic-emit phase surfaces as a
    structured RuntimeError, not a raw stacktrace.

    Locks the L5 contract. The synthetic emit block in
    ``verify_observability_exports`` exists so ``force_flush`` has data
    to push (without it, an empty buffer returns True trivially and the
    probe gives false confidence). Each emit is wrapped in
    ``try/except Exception: failures.append(...)`` precisely so a
    broken instrument (proxy not yet swapped, SDK API drift, exporter
    shutdown race) cannot crash the container before the diagnostic
    message renders. A regression that stripped the noqa+except would
    fail here.
    """
    from unittest.mock import MagicMock, patch

    from app.core import observability as obs

    settings = _settings_with_otel(monkeypatch, ENVIRONMENT="production")
    _patch_all_providers(monkeypatch)
    # Drive the metrics-emit arm into the exception path by making the
    # synthetic counter's add raise. Patching create_counter to return
    # a mock whose add raises is the cleanest way; the existing
    # PROFILING_INIT_FAILURES / FRONTEND_OBS_FAILURES module-level
    # counters are unaffected.
    broken_counter = MagicMock()
    broken_counter.add = MagicMock(side_effect=RuntimeError("simulated SDK drift"))
    with patch.object(obs._meter, "create_counter", return_value=broken_counter):
        with pytest.raises(RuntimeError, match=r"metrics-emit \(.*simulated SDK drift"):
            obs.verify_observability_exports(settings)


def test_trace_context_lock_serialises_concurrent_first_warnings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``_TRACE_CONTEXT_LOCK`` makes the once-and-quiet contract hold
    under concurrent failures.

    The processor's check-then-set on ``_TRACE_CONTEXT_WARNED`` is
    NOT atomic across threads even with CPython's GIL — two threads
    can both read False, both flip True, both emit "first failure"
    warnings. The lock around the check-then-set was added
    specifically for this case (uvicorn's thread-pool executor runs
    sync routes concurrently even with WEB_CONCURRENCY=1). Without
    the lock, an unlucky concurrent burst would spam multiple "first
    failure" warnings — exactly the spam the once-and-quiet
    contract is supposed to prevent.

    The existing single-threaded test ("warns only once on repeated
    get-span failures") proves the sentinel works sequentially, not
    that the lock prevents the documented race. This test spawns 8
    threads that all call the processor with a broken
    _get_current_span; asserts exactly one warning lands in caplog
    despite 8 concurrent first-failure attempts. A regression that
    removed the lock would fail here.
    """
    import threading

    from app.core import observability as obs

    # Per the global conftest autouse fixture, _TRACE_CONTEXT_WARNED
    # starts False.
    assert obs._TRACE_CONTEXT_WARNED is False

    barrier = threading.Barrier(8)

    def _broken_get_span() -> Any:
        raise RuntimeError("simulated concurrent first failure")

    def _hit_processor() -> None:
        barrier.wait()
        obs._structlog_processor_trace_context(
            None,
            "info",
            {"event": "concurrent"},
            _get_current_span=_broken_get_span,
        )

    threads = [threading.Thread(target=_hit_processor) for _ in range(8)]
    with caplog.at_level(logging.WARNING, logger="app.core.observability"):
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

    matching = [
        rec for rec in caplog.records
        if "structlog trace_id stamping disabled" in rec.getMessage()
    ]
    assert len(matching) == 1, [rec.getMessage() for rec in matching]


def test_setup_metrics_exporter_is_idempotent_within_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second call to setup_metrics_exporter must NOT install a second
    PeriodicExportingMetricReader.
    OTel's ``metrics.set_meter_provider`` is process-wide set-once and
    silently no-ops a second call — but the per-call build of
    OTLPMetricExporter + PeriodicExportingMetricReader still happens,
    leaking a background ticker thread. The fix flips
    ``_METRICS_EXPORTER_INSTALLED`` to True after the first install so
    subsequent calls early-return.
    """
    from unittest.mock import MagicMock, patch

    from app.core import observability as obs
    settings = _settings_with_otel(monkeypatch)
    fake_exporter = MagicMock()
    fake_exporter.export.return_value = None
    fake_exporter.shutdown.return_value = None
    fake_exporter._preferred_temporality = {}
    fake_exporter._preferred_aggregation = {}
    set_mp_calls: list[Any] = []
    def _capture(provider: Any) -> None:
        set_mp_calls.append(provider)
        provider.shutdown()
    with (
        patch(
            "opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter",
            return_value=fake_exporter,
        ),
        patch.object(otel_metrics, "set_meter_provider", _capture),
    ):
        obs.setup_metrics_exporter(settings)
        obs.setup_metrics_exporter(settings)
        obs.setup_metrics_exporter(settings)
    assert len(set_mp_calls) == 1, (
        f"setup_metrics_exporter installed the provider {len(set_mp_calls)} "
        "times; expected 1"
    )
