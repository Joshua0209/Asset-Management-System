"""Observability wiring for the FastAPI backend (W6 Phase 3, OTLP-native).

This module is the only place observability libraries are imported. Routes
talk to counters via the module-level singletons; ``app/main.py`` calls the
``setup_*`` functions in a fixed order (logging → log_exporter → metrics →
metrics_exporter → tracing → profiling). Splitting the concerns into
separate functions lets unit tests pin each piece without touching the
prod-image hot path.

Locked decisions from ``docs/plans/observability-prod-migration-plan.md``:

* **OTLP-native, single backend.** Traces, metrics, logs, and profiles
  push direct to Grafana Cloud from both local dev and production ECS.
  There is no ``/metrics`` route and no Alloy collector. Same exporter
  config in both environments; only the ``environment`` resource
  attribute and credentials differ.
* **Backend stays single-worker.** The ``WEB_CONCURRENCY=1`` invariant in
  ``app/main.py`` still holds — slowapi's MemoryStorage needs it, and so
  does Pyroscope's sampling thread (it would die in each worker fork
  otherwise).
* **All exporters are opt-in.** Lazy import + early return on flag-off so
  a credential-less developer boot is silent. ``OTEL_ENABLED=false`` is
  the dev default.

Metric naming: OTel instruments are created with dot-style names
(``http.server.duration``); the metrics exporter applies ``View`` rules
to publish them as Prom-style underscored names
(``http_server_duration_seconds``) so dashboard queries written against
the old prometheus-fastapi-instrumentator output keep working unchanged.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

import structlog
from opentelemetry import metrics

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.core.config import Settings

logger = logging.getLogger(__name__)

_TRACE_CONTEXT_WARNED: bool = False
# Lock around the check-then-set on ``_TRACE_CONTEXT_WARNED``. CPython's
# GIL makes a bare assignment atomic, but the *check-then-set* pattern
# (``if not _TRACE_CONTEXT_WARNED: _TRACE_CONTEXT_WARNED = True``)
# is not — two threads can both read False and both emit "first
# failure" warnings. The file's TODO at ``maybe_setup_profiling``
# contemplates relaxing ``WEB_CONCURRENCY=1``, after which this
# would matter; uvicorn also runs sync routes on a thread-pool
# executor today, so concurrent failures are technically possible
# even single-worker. Cheap insurance.
_TRACE_CONTEXT_LOCK = threading.Lock()
_METRICS_EXPORTER_INSTALLED: bool = False
_LOG_EXPORTER_INSTALLED: bool = False
_TRACING_INSTALLED: bool = False
# Bounded LRU-style cache for the Resource. The cache is keyed by the
# resource-identifying tuple; in prod the same tuple is computed three
# times during startup (once per ``setup_*_exporter``) and the cache
# saves three calls into OTel's host/process auto-detection. The test
# suite cycles through a handful of (replica_id, app_version,
# environment) combinations — the explicit upper bound keeps a
# pathological future test that loops over many combos from growing
# the cache unboundedly.
_RESOURCE_CACHE_MAX = 8
_RESOURCE_CACHE: dict[tuple[str, str, str, str], Any] = {}


# ---------------------------------------------------------------------------
# Module-level counters (OTel native)
#
# Counters are created at import time so routes can do
# ``from app.core.observability import OPTIMISTIC_CONFLICTS`` without
# guarding on a setup-was-called check.
#
# Before ``setup_metrics_exporter`` runs, ``metrics.get_meter`` returns the
# global ``ProxyMeter``; its ``create_counter`` returns a ``ProxyCounter``
# that lazily rebinds to whichever MeterProvider is installed later. Every
# ``.add(...)`` issued before installation silently no-ops, and every
# ``.add(...)`` after installation flows into the real exporter. When
# telemetry is off (``OTEL_ENABLED=false`` is the dev default), increments
# stay invisible by design — counters are always callable, never raise.
# ---------------------------------------------------------------------------

_meter = metrics.get_meter("ams.backend")

FSM_TRANSITIONS = _meter.create_counter(
    "ams_fsm_transitions_total",
    description=(
        "Successful repair-request FSM transitions. "
        "Attributes: state_from, state_to (enum names), asset_kind."
    ),
)
"""OTel counter for FSM state changes.

Call sites attach attributes per ``.add(1, attributes={...})``:

* ``state_from`` / ``state_to``: enum names (``PENDING_REVIEW``,
  ``UNDER_REPAIR``, …), taken from ``RepairRequestStatus.<X>.name`` so a
  rename in the enum surfaces here at type-check time. The submit flow
  uses the sentinel literal ``"NONE"`` for ``state_from`` because the
  repair request did not previously exist; dashboards can count
  creations without collapsing them into other PENDING_REVIEW arrivals.

  Naming note: keys are ``state_from`` / ``state_to`` rather than the
  shorter ``from`` / ``to`` because ``from`` is a Python reserved word
  (annoying as a key inside ``.add(attributes=dict(...))`` form) and
  both names collide with PromQL/LogQL parser keywords in some query
  contexts. The ``state_*`` prefix also makes Grafana variable templates
  unambiguous about which attribute they bind to.
* ``asset_kind``: currently always ``"repair_request"`` — only repair-
  request transitions are instrumented today. Reserved for direct
  asset-state transitions if/when those are instrumented.
"""

OPTIMISTIC_CONFLICTS = _meter.create_counter(
    "ams_optimistic_conflicts_total",
    description=(
        "409 conflicts raised by mutating endpoints (optimistic-lock losses, "
        "duplicate-request guards, invalid FSM transitions). Attributes: "
        "endpoint, code."
    ),
)
"""OTel counter for 409 conflicts.

* ``endpoint``: **module-scoped today** — the value is whatever the
  per-module ``_conflict`` helper defaults to (``"assets"`` or
  ``"repair_requests"``). Slice by ``code`` for granular dashboards.
* ``code``: the granular error code from the project envelope
  (``duplicate_request``, ``invalid_transition``, ``version_conflict``,
  …). Matches ``docs/system-design/12-api-design.md`` §"409 Conflict".
"""

FRONTEND_OBS_FAILURES = _meter.create_counter(
    "ams_frontend_observability_init_failures_total",
    description=(
        "Frontend OTel SDK init failures reported via the browser beacon "
        "POST /api/v1/observability/client-error. Attributes: kind (free-form "
        "subcategory the browser sends, currently always "
        "'observability_init_failed')."
    ),
)
"""OTel counter for browser-side observability init failures.

Incremented by ``POST /api/v1/observability/client-error`` whenever the
frontend's ``initObservability`` catch block fires. The browser-side
OTLP SDK has no way to report its own init failure back to GC (CORS,
no auth, no fallback channel), so without this beacon a misconfigured
prod bundle silently disables tracing for 100% of users —
indistinguishable from ``VITE_OTEL_ENABLED=false``. Operators alert on
``rate(ams_frontend_observability_init_failures_total[5m]) > 0`` to
catch a regression in the next deploy.
"""

PROFILING_INIT_FAILURES = _meter.create_counter(
    "ams_profiling_init_failures_total",
    description=(
        "Pyroscope profiling init failures during ``maybe_setup_profiling``. "
        "Attributes: reason ('missing_dependency' when pyroscope-io is not "
        "installed, 'configure_error' when pyroscope.configure raises)."
    ),
)
"""OTel counter for backend Pyroscope profiling init failures.

The pyroscope-io client runs in a background sampling thread with no
synchronous health surface — ``verify_observability_exports`` cannot
probe it the way it probes OTLP. Without this counter the only signal
that profiling silently went dark in prod is one WARN line at boot,
which scrolls off the operator's dashboard in minutes. Alert on
``rate(ams_profiling_init_failures_total[5m]) > 0`` to catch a missing
``pyroscope-io`` wheel or a bad token in the next deploy.
"""


# ---------------------------------------------------------------------------
# Tracing helpers
# ---------------------------------------------------------------------------


class _SpanProto(Protocol):
    """Subset of ``opentelemetry.trace.Span`` we depend on.

    Declared so the structlog processor can be unit-tested without
    importing OpenTelemetry's heavy machinery — the test injects a fake
    that quacks like this.
    """

    def get_span_context(self) -> Any: ...  # pragma: no cover - protocol shape


def _real_get_current_span() -> _SpanProto:
    """Adapter so the structlog processor can be mocked.

    Imported lazily because ``opentelemetry.trace`` triggers the OTel
    global tracer bootstrap on first import — we want that cost paid in
    ``setup_tracing``, not on plain log calls.
    """
    from opentelemetry import trace as otel_trace

    return otel_trace.get_current_span()


def _structlog_processor_trace_context(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
    *,
    _get_current_span: Callable[[], _SpanProto] = _real_get_current_span,
) -> dict[str, Any]:
    """Structlog processor: stamp the active OTLP trace_id / span_id.

    Skips silently when no span is active or the span context is invalid
    so that pre-startup boot logs (which run before ``setup_tracing``)
    aren't decorated with a bogus all-zeros trace.

    Runs BEFORE the OTel ``LoggingHandler`` picks up the formatted record,
    so ``trace_id`` is on the ``LogRecord``'s ``extra`` payload when the
    bridge forwards it to Grafana Cloud Loki. If you move this processor
    out of the chain, the bridge still works (the OTel SDK reads the
    active span itself via ``LogRecord.trace_id``), but human-readable
    text logs lose the trace correlation field.
    """
    try:
        span = _get_current_span()
    except (AttributeError, ImportError, RuntimeError) as exc:
        # Narrow on the realistic failure modes (OTel API drift,
        # uninstalled SDK, recursive logging during bootstrap). Surface
        # the first failure once so a misconfig doesn't hide forever;
        # subsequent calls stay silent so a broken install doesn't spam
        # the log on every request. Lock-protected because the check-
        # then-set is not atomic across threads.
        global _TRACE_CONTEXT_WARNED
        should_warn = False
        with _TRACE_CONTEXT_LOCK:
            if not _TRACE_CONTEXT_WARNED:
                _TRACE_CONTEXT_WARNED = True
                should_warn = True
        if should_warn:
            logger.warning(
                "structlog trace_id stamping disabled — first failure: %s",
                exc,
            )
        return event_dict
    ctx = getattr(span, "get_span_context", lambda: None)()
    if ctx is None or not getattr(ctx, "is_valid", False):
        return event_dict
    trace_id = getattr(ctx, "trace_id", 0)
    span_id = getattr(ctx, "span_id", 0)
    if trace_id:
        event_dict["trace_id"] = f"{trace_id:032x}"
    if span_id:
        event_dict["span_id"] = f"{span_id:016x}"
    return event_dict


def _build_resource(settings: Settings) -> Any:
    """Common Resource for traces, metrics, and logs.

    Centralised so every signal carries the same ``service.name``,
    ``service.instance.id``, ``service.version``, and ``environment``
    attributes — that's what makes ``$environment=production`` work as a
    single template variable across all six Grafana Cloud dashboards.

    Cached by the resource-identifying tuple so the OTel SDK's host /
    process auto-detection doesn't run three times at boot (once per
    setup_*_exporter call site). The cache has an explicit upper
    bound (``_RESOURCE_CACHE_MAX``); on overflow the oldest entry is
    evicted — keeps a pathological future test that loops over many
    (replica_id, app_version, environment) combinations from growing
    the cache unboundedly.
    """
    key = (
        "ams-backend",
        settings.replica_id,
        settings.app_version,
        settings.environment,
    )
    cached = _RESOURCE_CACHE.get(key)
    if cached is not None:
        return cached

    from opentelemetry.sdk.resources import Resource

    resource = Resource.create(
        {
            "service.name": key[0],
            "service.instance.id": key[1],
            "service.version": key[2],
            "environment": key[3],
        }
    )
    # Evict the oldest entry when at capacity. dict preserves insertion
    # order in Python 3.7+, so ``next(iter(...))`` is the oldest key.
    if len(_RESOURCE_CACHE) >= _RESOURCE_CACHE_MAX:
        del _RESOURCE_CACHE[next(iter(_RESOURCE_CACHE))]
    _RESOURCE_CACHE[key] = resource
    return resource


# ---------------------------------------------------------------------------
# Public setup_* API
# ---------------------------------------------------------------------------


def setup_logging(settings: Settings) -> None:
    """Configure structlog to emit JSON (prod) or key=value text (dev/pytest).

    Application logs flow through structlog's stdlib bridge so every record
    that hits the root logger shares one JSON shape. Uvicorn's plaintext
    access logger is silenced: per-request observability comes from OTel
    HTTP server metrics (rate / error / duration) plus OTLP spans when
    ``otel_enabled`` is on. ``setup_log_exporter`` later attaches an OTel
    ``LoggingHandler`` to the same root logger so every structlog event
    flows to Grafana Cloud Loki without a second emit path.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _structlog_processor_trace_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Replace existing handlers so repeated calls (pytest re-imports the
    # app inside multiple TestClient sessions) don't duplicate output.
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Drop uvicorn's plaintext access line. OTel HTTP server metrics +
    # OTLP spans + Loki access logs (from the FE nginx side) cover
    # per-request observability; the access line would be duplicate noise.
    for noisy in ("uvicorn.access",):
        access_logger = logging.getLogger(noisy)
        access_logger.handlers.clear()
        access_logger.propagate = False


def setup_log_exporter(settings: Settings) -> None:
    """Bridge stdlib logging → OTel logs → Grafana Cloud Loki via OTLP.

    No-op when ``settings.otel_enabled`` is False so credential-less local
    dev stays quiet and the dev image avoids the OTLP exporter's
    background threads.

    Idempotent: tracked via ``_LOG_EXPORTER_INSTALLED`` so a second call
    inside the same process (pytest re-imports, dev reload) doesn't stack
    a second ``LoggingHandler`` on the root logger or leak the previous
    BatchLogRecordProcessor's background thread.

    Ordering: must run AFTER ``setup_logging`` (so the OTel
    ``LoggingHandler`` is added on top of the structlog ProcessorFormatter
    handler, not displaced by it) and BEFORE any further log call from
    application code (so early events still reach Loki). Structlog's
    ``_structlog_processor_trace_context`` already stamps ``trace_id`` on
    the formatted record, so the bridge forwards it to Loki labels
    automatically. The OTel ``LogRecord`` also carries ``trace_id`` /
    ``span_id`` natively when a span is active, which is what powers the
    Loki → Tempo "view trace" jump in Explore.
    """
    if not settings.otel_enabled:
        return

    global _LOG_EXPORTER_INSTALLED
    if _LOG_EXPORTER_INSTALLED:
        logger.debug("OTel log exporter already installed; skipping re-install.")
        return

    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    provider = LoggerProvider(resource=_build_resource(settings))
    exporter = OTLPLogExporter(
        endpoint=settings.otel_endpoint,
        headers=settings.otel_exporter_otlp_headers.get_secret_value() or None,
    )
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    set_logger_provider(provider)
    # Flip the install flag IMMEDIATELY after the irreversible
    # set_logger_provider call (OTel's set_logger_provider is process-wide
    # set-once; a second call silently no-ops). If the subsequent
    # addHandler raises (root logger in a degenerate state — rare), we
    # want a retry to early-return rather than re-running set_logger_provider
    # against a now-leaked second LoggerProvider. The lost addHandler is
    # surfaced as an uncaught exception to the caller, not silently
    # swallowed under a half-installed state.
    _LOG_EXPORTER_INSTALLED = True

    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
    logging.getLogger().addHandler(handler)


def setup_metrics(app: FastAPI, settings: Settings) -> None:
    """Wire FastAPI HTTP server metrics + spans via OTel.

    No-op when ``settings.otel_enabled`` is False — the no-op MeterProvider
    that's active by default still lets module-level counters (FSM and
    OPTIMISTIC_CONFLICTS) be called without raising, they just record into
    nothing. This keeps dev/pytest free of the FastAPI instrumentor's
    per-request overhead.

    The instrumentor emits dot-style names (``http.server.duration``,
    ``http.server.active_requests``); ``setup_metrics_exporter``'s
    ``View`` rules rename them to the Prom-style series the existing
    dashboards query.

    Configured options (security + cardinality):

    * ``http_capture_headers_sanitize_fields`` redacts sensitive request /
      response headers to ``[REDACTED]`` *if* header capture is ever
      enabled (currently off by default but controllable via the
      ``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST`` env
      var or a future SDK default flip). The regex list covers the
      bearer-token / cookie / API-key shapes a Grafana Cloud Tempo
      reader must never see. Hard-coded via kwarg rather than env so
      it cannot be silently turned off in an ECS task def.
    * ``excluded_urls`` skips the ALB liveness/readiness probes — they
      run every few seconds, dominate span volume, and carry no
      diagnostic value (success is the boring case; failure surfaces
      via the existing /ready 503 path, not via spans).
    """
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app,
        # Also skip the frontend-failure beacon: it would create a
        # circular telemetry loop (the beacon's own request would
        # generate a span / metric that, if export then failed, could
        # trigger another beacon — runaway feedback).
        excluded_urls="/health,/ready,/api/v1/observability/client-error",
        http_capture_headers_sanitize_fields=[
            ".*authorization.*",
            ".*cookie.*",
            ".*x-api-key.*",
            ".*proxy-authorization.*",
            ".*set-cookie.*",
        ],
    )


def setup_metrics_exporter(settings: Settings) -> None:
    """Install the OTel MeterProvider that pushes metrics to Grafana Cloud.

    No-op when ``settings.otel_enabled`` is False. Idempotent across pytest
    re-imports — tracked via ``_METRICS_EXPORTER_INSTALLED`` because
    ``metrics.set_meter_provider`` is process-wide set-once and silently
    no-ops the second call; without this guard, a re-import would leak
    the previous ``PeriodicExportingMetricReader``'s background thread.

    Views rename the OTel HTTP server instruments to the Prom-style names
    the existing Grafana dashboards already query. The SDK's internal
    instrument name stays dot-style; only the exposed Prom series is
    renamed.
    """
    if not settings.otel_enabled:
        return

    global _METRICS_EXPORTER_INSTALLED
    if _METRICS_EXPORTER_INSTALLED:
        logger.debug("MeterProvider already installed; skipping re-install.")
        return

    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.metrics.view import View

    views = [
        View(
            instrument_name="http.server.duration",
            name="http_server_duration_seconds",
        ),
        View(
            instrument_name="http.server.request.duration",
            name="http_server_duration_seconds",
        ),
        View(
            instrument_name="http.server.active_requests",
            name="ams_http_requests_inprogress",
        ),
    ]

    exporter = OTLPMetricExporter(
        endpoint=settings.otel_endpoint,
        headers=settings.otel_exporter_otlp_headers.get_secret_value() or None,
    )
    reader = PeriodicExportingMetricReader(exporter)
    provider = MeterProvider(
        resource=_build_resource(settings),
        metric_readers=[reader],
        views=views,
    )
    metrics.set_meter_provider(provider)
    _METRICS_EXPORTER_INSTALLED = True


def setup_tracing(app: FastAPI, settings: Settings) -> None:
    """Wire OTLP tracing for FastAPI + SQLAlchemy.

    No-op when ``settings.otel_enabled`` is False — keeps the dev image
    free of the OTLP exporter's background threads and the SQLAlchemy
    instrumentor's per-query overhead. The dev test suite runs with the
    flag off so SQLite event hooks don't trip.

    Idempotent: tracked via ``_TRACING_INSTALLED`` because
    ``trace.set_tracer_provider`` is process-wide set-once and the
    SQLAlchemy instrumentor double-instruments engines on a second call.
    """
    if not settings.otel_enabled:
        return

    global _TRACING_INSTALLED
    if _TRACING_INSTALLED:
        logger.debug("TracerProvider already installed; skipping re-install.")
        return

    from opentelemetry import trace as otel_trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=_build_resource(settings))
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_endpoint,
        headers=settings.otel_exporter_otlp_headers.get_secret_value() or None,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    otel_trace.set_tracer_provider(provider)
    # Flip the install flag IMMEDIATELY after set_tracer_provider — that's
    # the irreversible step (OTel's set_tracer_provider is process-wide
    # set-once and warns + no-ops on re-call). If the subsequent
    # SQLAlchemyInstrumentor instrument raises (engine already
    # instrumented from a prior test, dependency version mismatch), we
    # want a retry to early-return rather than re-running
    # set_tracer_provider against a leaked second TracerProvider AND
    # double-instrumenting the SQLAlchemy engine. The exception from
    # instrument() propagates to the caller.
    _TRACING_INSTALLED = True

    # SQLAlchemy instrumentation hooks into the engine; importing the
    # engine here (rather than at module top) avoids the circular
    # `app.main → observability → db.session → app.main` chain.
    from app.db.session import engine

    SQLAlchemyInstrumentor().instrument(engine=engine)


def maybe_setup_profiling(settings: Settings) -> None:
    """Start the Pyroscope sampling thread when enabled.

    Wrapped in try/except so the dev image (which doesn't ship the
    optional ``pyroscope-io`` extra) only logs a warning instead of
    crashing on import. Configure failures (bad token, unreachable
    server) are also caught and logged so a profiling misconfig never
    crashes the request-serving path.

    Enabled in production as of Phase 3 of the prod migration plan
    (reverses the original W6 "off in prod" locked decision). The
    ``WEB_CONCURRENCY=1`` invariant in ``app/main.py`` plus the absence
    of ``gunicorn --preload`` means the sampling thread starts inside
    the worker post-fork. If samples don't appear in production within
    60s of first request, the fallback is the ``gunicorn.conf.py``
    ``post_fork`` hook documented in the Phase 4 plan.

    TODO: before relaxing ``WEB_CONCURRENCY=1`` to enable multi-worker
    gunicorn, add the ``post_fork`` hook (see Phase 4 migration plan
    §"Pyroscope post-fork"). Without it, the sampling thread dies in
    every worker after fork and profiling silently goes dark.
    """
    if not settings.pyroscope_enabled:
        return
    try:
        import pyroscope
    except ImportError:
        logger.warning(
            "PYROSCOPE_ENABLED=true but pyroscope-io is not installed. "
            "Install the `prod` extra to enable continuous profiling."
        )
        PROFILING_INIT_FAILURES.add(1, attributes={"reason": "missing_dependency"})
        return
    try:
        pyroscope.configure(
            application_name=f"ams-backend.{settings.replica_id}",
            server_address=settings.pyroscope_server,
            basic_auth_username=settings.pyroscope_basic_auth_username,
            auth_token=settings.pyroscope_auth_token.get_secret_value(),
        )
    except (RuntimeError, OSError, ValueError) as exc:
        # Narrowed from a bare ``Exception``: pyroscope-io's known failure
        # modes are bad-token / unreachable-server (RuntimeError), socket
        # / DNS issues (OSError), and malformed-server-URL (ValueError).
        # A TypeError would imply this code passed wrong kwargs — a
        # programmer bug that should propagate, not be swallowed.
        logger.warning(
            "Pyroscope configure failed; continuous profiling disabled: %s",
            exc,
        )
        PROFILING_INIT_FAILURES.add(1, attributes={"reason": "configure_error"})


def verify_observability_exports(settings: Settings) -> None:
    """Smoke-test the OTLP exporters at startup; fail-loud on failure.

    Runs only when ``settings.otel_enabled`` is true and
    ``settings.environment != "local"``. Emits one synthetic span,
    metric, and log record per signal first (so the BatchProcessors and
    PeriodicExportingMetricReader actually have data to push to Grafana
    Cloud), then calls ``force_flush(5_000)`` on every installed
    provider. Any ``False`` return raises ``RuntimeError`` so the ECS
    task crashes before the rolling-deploy gate marks it healthy.

    Why the synthetic emit matters: ``force_flush`` on an empty buffer
    returns ``True`` trivially — the SDK has nothing to send, so a
    completely wrong API key still produces a "passing" probe. The
    real export error surfaces only on the first actual push. Emitting
    first means a wrong API key produces a real export attempt, which
    fails, which makes ``force_flush`` return ``False``, which crashes
    the task. This is what closes the silent-export-failure gap.

    The synthetic signals carry attribute ``ams.probe="startup"`` so
    they're trivially filterable in Grafana Cloud (e.g. exclude from
    dashboards with ``{ams.probe!="startup"}``).

    Local-with-otel-on is exempt so a developer pointing at a
    self-hosted Tempo without strict creds keeps an interactive boot.
    Safe to call from main.py after ``setup_*_exporter``.
    """
    if not settings.otel_enabled or settings.environment == "local":
        return

    # Assert each exporter actually installed before flushing. The original
    # implementation used ``getattr(provider, "force_flush", None)`` and a
    # ``callable`` guard, which silently skipped any signal whose exporter
    # had failed to install and left the global no-op ProxyProvider in
    # place — the exact silent-export-failure class this function exists
    # to catch. If a signal's ``setup_*_exporter`` raised or never ran, the
    # task must crash here, not boot with that signal dark.
    missing: list[str] = []
    if not _METRICS_EXPORTER_INSTALLED:
        missing.append("metrics")
    if not _TRACING_INSTALLED:
        missing.append("traces")
    if not _LOG_EXPORTER_INSTALLED:
        missing.append("logs")
    if missing:
        raise RuntimeError(
            f"OTLP exporter not installed for: {', '.join(missing)}. "
            "setup_log_exporter / setup_metrics_exporter / setup_tracing must "
            "complete before verify_observability_exports — check earlier "
            "startup logs for the failure that left the no-op provider in place."
        )

    # Lazy imports for the same reason setup_* are lazy: keep dev images
    # free of the OTLP SDK's import cost when the flag is off.
    from opentelemetry import metrics as otel_metrics
    from opentelemetry import trace as otel_trace
    from opentelemetry._logs import get_logger_provider

    # --- Synthetic emit: one signal of each kind. ----------------------
    probe_attrs = {"ams.probe": "startup"}
    failures: list[str] = []

    # Each synthetic emit is independently guarded — a broken instrument
    # (proxy not yet swapped, SDK API drift, exporter shutdown race) must
    # surface as a structured failure on the RuntimeError below, not as a
    # bare stack trace that crashes the container before the diagnostic
    # message renders. Same fail-loud contract; richer error payload.
    try:
        probe_counter = _meter.create_counter(
            "ams_observability_probe_total",
            description=(
                "Synthetic increment from verify_observability_exports. "
                "Always 1 per process start when OTEL is enabled in non-local "
                "environments. Filter out of dashboards with ams.probe!=startup."
            ),
        )
        probe_counter.add(1, attributes=probe_attrs)
    except Exception as exc:  # noqa: BLE001 - structured failure aggregation
        failures.append(f"metrics-emit ({exc!r})")

    try:
        tracer = otel_trace.get_tracer("ams.backend.probe")
        with tracer.start_as_current_span("observability_probe") as span:
            for key, value in probe_attrs.items():
                span.set_attribute(key, value)
    except Exception as exc:  # noqa: BLE001 - structured failure aggregation
        failures.append(f"traces-emit ({exc!r})")

    try:
        logger.info(
            "Observability startup probe — synthetic signal for OTLP export check.",
            extra=probe_attrs,
        )
    except Exception as exc:  # noqa: BLE001 - structured failure aggregation
        failures.append(f"logs-emit ({exc!r})")

    # --- Flush and fail loudly if any signal failed to push. -----------
    # The installed-flag assertions above already proved each provider is
    # real, not the global no-op ProxyProvider, so ``force_flush`` is
    # guaranteed to exist as a callable. A missing attribute now is a
    # programming error (SDK version regression) and surfaces as
    # AttributeError — which is what we want.
    meter_provider = otel_metrics.get_meter_provider()
    if not meter_provider.force_flush(5_000):  # type: ignore[attr-defined]
        failures.append("metrics-flush")

    tracer_provider = otel_trace.get_tracer_provider()
    if not tracer_provider.force_flush(5_000):  # type: ignore[attr-defined]
        failures.append("traces-flush")

    logger_provider = get_logger_provider()
    if not logger_provider.force_flush(5_000):  # type: ignore[attr-defined]
        failures.append("logs-flush")

    if failures:
        raise RuntimeError(
            f"OTLP startup probe failed for: {', '.join(failures)}. "
            f"Verify OTEL_ENDPOINT={settings.otel_endpoint!r} is reachable "
            "and OTEL_EXPORTER_OTLP_HEADERS authenticates against Grafana Cloud."
        )
