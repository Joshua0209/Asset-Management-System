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
import logging.config
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

import structlog
from opentelemetry import metrics

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.core.config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level counters (OTel native)
#
# Counters are created at import time so routes can do
# ``from app.core.observability import OPTIMISTIC_CONFLICTS`` without
# guarding on a setup-was-called check; missing instrumentation becomes a
# startup error, not a silent miss at runtime.
#
# Before ``setup_metrics_exporter`` runs, ``metrics.get_meter`` returns the
# default no-op meter, so the counters silently no-op until a real
# MeterProvider is installed. This matches the prometheus_client default
# registry behaviour the module used previously.
# ---------------------------------------------------------------------------

_meter = metrics.get_meter("ams.backend")

FSM_TRANSITIONS = _meter.create_counter(
    "ams_fsm_transitions_total",
    description=(
        "Successful asset / repair-request FSM transitions. "
        "Attributes: from, to (enum names), asset_kind ('asset' vs "
        "'repair_request')."
    ),
)
"""OTel counter for FSM state changes.

Call sites attach attributes per ``.add(1, attributes={...})``:

* ``from`` / ``to``: enum names (``PENDING_REVIEW``, ``UNDER_REPAIR``, …).
* ``asset_kind``: ``asset`` for direct asset transitions, ``repair_request``
  for repair-request transitions. Lets the Repair Journey dashboard slice
  the two streams without a regex on the metric name.
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
    except Exception:  # noqa: BLE001 — never let a log call raise
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
    """
    from opentelemetry.sdk.resources import Resource

    return Resource.create(
        {
            "service.name": "ams-backend",
            "service.instance.id": settings.replica_id,
            "service.version": settings.app_version,
            "environment": settings.environment,
        }
    )


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

    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
    logging.getLogger().addHandler(handler)


def setup_metrics(app: FastAPI, settings: Settings) -> None:
    """Wire FastAPI HTTP server metrics via OTel.

    No-op when ``settings.otel_enabled`` is False — the no-op MeterProvider
    that's active by default still lets module-level counters (FSM and
    OPTIMISTIC_CONFLICTS) be called without raising, they just record into
    nothing. This keeps dev/pytest free of the FastAPI instrumentor's
    per-request overhead.

    The instrumentor emits dot-style names (``http.server.duration``,
    ``http.server.active_requests``); ``setup_metrics_exporter``'s
    ``View`` rules rename them to the Prom-style series the existing
    dashboards query.
    """
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)


def setup_metrics_exporter(settings: Settings) -> None:
    """Install the OTel MeterProvider that pushes metrics to Grafana Cloud.

    No-op when ``settings.otel_enabled`` is False. Idempotent across pytest
    re-imports because we only install when no real provider has been
    configured yet — repeated calls would otherwise leak background
    exporter threads.

    Views rename the OTel HTTP server instruments to the Prom-style names
    the existing Grafana dashboards already query. The SDK's internal
    instrument name stays dot-style; only the exposed Prom series is
    renamed.
    """
    if not settings.otel_enabled:
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


def setup_tracing(app: FastAPI, settings: Settings) -> None:
    """Wire OTLP tracing for FastAPI + SQLAlchemy.

    No-op when ``settings.otel_enabled`` is False — keeps the dev image
    free of the OTLP exporter's background threads and the SQLAlchemy
    instrumentor's per-query overhead. The dev test suite runs with the
    flag off so SQLite event hooks don't trip.
    """
    if not settings.otel_enabled:
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

    # SQLAlchemy instrumentation hooks into the engine; importing the
    # engine here (rather than at module top) avoids the circular
    # `app.main → observability → db.session → app.main` chain.
    from app.db.session import engine

    SQLAlchemyInstrumentor().instrument(engine=engine)


def maybe_setup_profiling(settings: Settings) -> None:
    """Start the Pyroscope sampling thread when enabled.

    Wrapped in try/except so the dev image (which doesn't ship the
    optional ``pyroscope-io`` extra) only logs a warning instead of
    crashing on import.

    Enabled in production as of Phase 3 of the prod migration plan
    (reverses the original W6 "off in prod" locked decision). The
    ``WEB_CONCURRENCY=1`` invariant in ``app/main.py`` plus the absence
    of ``gunicorn --preload`` means the sampling thread starts inside
    the worker post-fork. If samples don't appear in production within
    60s of first request, the fallback is the ``gunicorn.conf.py``
    ``post_fork`` hook documented in the Phase 4 plan.
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
        return
    pyroscope.configure(
        application_name=f"ams-backend.{settings.replica_id}",
        server_address=settings.pyroscope_server,
        basic_auth_username=settings.pyroscope_basic_auth_username,
        auth_token=settings.pyroscope_auth_token.get_secret_value(),
    )
