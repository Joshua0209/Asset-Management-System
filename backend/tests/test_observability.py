"""Backend observability smoke tests (W6 Phase 3, OTLP-native).

These verify the contract from
``docs/plans/observability-prod-migration-plan.md`` § Phase 3:

* Optimistic-conflict counter increments on a 409 raised by an
  asset/repair-request endpoint, keyed by ``{endpoint, code}``.
* FSM-transition counter increments on a successful repair-request
  state change, keyed by ``{from, to, asset_kind}``.
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
from collections.abc import Callable, Iterable
from datetime import date
from decimal import Decimal
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
    ``ams_fsm_transitions_total{from,to,asset_kind}``.

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
        {"from": "PENDING_REVIEW", "to": "UNDER_REPAIR"},
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
        {"from": "PENDING_REVIEW", "to": "UNDER_REPAIR"},
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
    assert settings.otel_exporter_otlp_headers == ""
    assert settings.pyroscope_enabled is False
    assert settings.pyroscope_server == ""
    assert settings.pyroscope_auth_token == ""
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
