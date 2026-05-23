"""Observability wiring for the FastAPI backend (W6 Phase 1).

This module is the only place observability libraries are imported. Routes
talk to counters via the module-level singletons; ``app/main.py`` calls the
``setup_*`` functions in a fixed order (logging → metrics → tracing →
profiling). Splitting the four concerns into separate functions lets the
middleware-order regression test pin them down without touching the
prod-image hot path.

Locked decisions from ``docs/plans/observability-implementation-plan.md``:

* Backend stays single-worker; aggregate at scrape time. Counters live in
  a per-process Prometheus registry — multi-worker would silently
  fragment them, same hazard as slowapi's MemoryStorage.
* ``/metrics`` is mounted but explicitly exempt from the slowapi limiter
  via ``@limiter.exempt``. Prometheus scrapes the endpoint every 15s by
  default; a 30-rpm anonymous tier would self-DoS the scrape inside two
  minutes.
* OTLP tracing and Pyroscope profiling are *both* opt-in. Lazy import +
  try/except so a missing extra in the dev image is a logged warning,
  not a crash.
"""

from __future__ import annotations

import logging
import logging.config
import sys
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol

import structlog
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.core.config import Settings

# ASGI primitives (kept inside a local alias block so the module stays
# importable from non-FastAPI contexts such as alembic env — Starlette's
# typing module is a hard dep here, fine since FastAPI already pulls it).
Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level counters
#
# Counters are created at import time so that:
#
#   1. Routes can `from app.core.observability import OPTIMISTIC_CONFLICTS`
#      without needing a setup-was-called check; missing instrumentation
#      becomes a startup error, not a silent miss at runtime.
#   2. The Prometheus default registry holds a single instance per label
#      tuple even if `setup_metrics` is invoked multiple times by tests.
# ---------------------------------------------------------------------------

FSM_TRANSITIONS = Counter(
    "ams_fsm_transitions_total",
    "Successful asset / repair-request FSM transitions.",
    labelnames=("from", "to", "asset_kind"),
)
"""Labelled counter for FSM state changes.

* ``from`` / ``to``: enum names (``PENDING_REVIEW``, ``UNDER_REPAIR``, …).
* ``asset_kind``: ``asset`` for direct asset transitions, ``repair_request``
  for repair-request transitions. Lets the Repair Journey dashboard slice
  the two streams without a regex on the metric name.
"""

OPTIMISTIC_CONFLICTS = Counter(
    "ams_optimistic_conflicts_total",
    "409 conflicts raised by mutating endpoints (optimistic-lock losses, "
    "duplicate-request guards, invalid FSM transitions).",
    labelnames=("endpoint", "code"),
)
"""Labelled counter for 409 conflicts.

* ``endpoint``: **module-scoped today** — the value is whatever the
  per-module ``_conflict`` helper defaults to (``"assets"`` or
  ``"repair_requests"``). This keeps the series low-cardinality and
  lets dashboards split by surface area, but it does NOT give
  route-template granularity (``POST /repair-requests`` vs
  ``POST /repair-requests/{id}/approve``). Route-level breakdown is
  a Phase-1-follow-up: helpers already accept an ``endpoint=...``
  kwarg, so callsites can be threaded through without a schema change.
  Until then, slice by ``code`` for granularity.
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

    The ``_get_current_span`` seam exists for unit testing only — production
    callers always take the default.
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


# ---------------------------------------------------------------------------
# Public setup_* API
# ---------------------------------------------------------------------------


def setup_logging(settings: Settings) -> None:
    """Configure structlog to emit JSON (prod) or key=value text (dev/pytest).

    Application logs flow through structlog's stdlib bridge so every record
    that hits the root logger shares one JSON shape. Uvicorn's plaintext
    access logger is silenced; per-request observability is split across
    three surfaces: the Prometheus ``/metrics`` endpoint covers RED (rate /
    error / duration), OTLP spans give per-request traces when
    ``otel_enabled`` is on, and the JSON access log emitted by
    :class:`AccessLogMiddleware` (registered in ``setup_access_log``) is
    what dashboards 03 / 04 consume — log lines tagged with the same
    ``trace_id`` Tempo holds, enabling the log → trace correlation drill.
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

    # Drop uvicorn's plaintext access line. /metrics (RED) and OTLP spans
    # cover per-request observability; the access line would just be
    # noise on top. See setup_logging docstring for the JSON-access-log
    # follow-up note.
    for noisy in ("uvicorn.access",):
        access_logger = logging.getLogger(noisy)
        access_logger.handlers.clear()
        access_logger.propagate = False


def setup_metrics(app: FastAPI) -> None:
    """Mount the Prometheus ``/metrics`` exposition.

    Called *after* ``SlowAPIMiddleware`` is registered so that scrape
    requests pass through the same middleware stack as user traffic —
    `@limiter.exempt` is then the one place the limiter is bypassed,
    matching the existing ``/health`` and ``/ready`` posture.
    """
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/health", "/ready"],
        inprogress_name="ams_http_requests_inprogress",
        inprogress_labels=True,
    )
    # Opt into the latency + request-count metrics explicitly and skip the
    # request/response size collectors. The bundled `metrics.default()` calls
    # ``int(Content-Length, 0)`` unguarded, so any caller that sends a
    # malformed header (the existing
    # tests/test_repair_requests::test_invalid_content_length_returns_422
    # regression test does exactly that) crashes the instrumentator
    # middleware with a ValueError and the 422 path never returns.
    # Dashboards rely on RED (rate / error / duration), so latency +
    # request count are the load-bearing metrics; payload size is a nice
    # to have that we can layer back in once a safe collector exists.
    from prometheus_fastapi_instrumentator import metrics

    instrumentator.add(metrics.latency())
    instrumentator.add(metrics.requests())
    instrumentator.instrument(app)

    # Lazy import so the slowapi dependency stays in app.main and this
    # module is importable from non-FastAPI contexts (e.g. alembic env).
    # Expose with a route function we own, then attach `@limiter.exempt`
    # to it. The instrumentator's own `.expose()` registers a private
    # handler whose object identity is hidden inside an internal
    # attribute, which `limiter.exempt` cannot mark. Owning the handler
    # is the only stable way to keep the exemption pinned across library
    # upgrades.
    #
    # No ``request: Request`` parameter: slowapi's ``@limiter.exempt`` is a
    # marker-only decorator (it doesn't wrap), so FastAPI inspects the raw
    # signature. Naming a parameter ``request`` would make FastAPI treat it
    # as a query param even when annotated as ``Request`` — slowapi's own
    # rewriting that normally rescues that case only fires for limited
    # routes, not exempt ones.
    from fastapi import Response
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        generate_latest,
    )

    from app.core.rate_limit import limiter

    @app.get("/metrics", include_in_schema=False)
    @limiter.exempt  # type: ignore[untyped-decorator]
    def metrics_endpoint() -> Response:
        """Prometheus exposition.

        Exempt from rate limiting (see module docstring) and excluded
        from the OpenAPI schema — scrape targets aren't part of the
        client-facing API surface.
        """
        return Response(
            content=generate_latest(REGISTRY),
            media_type=CONTENT_TYPE_LATEST,
        )


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
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.name": "ams-backend",
            "service.instance.id": settings.replica_id,
            "service.version": settings.app_version,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    otel_trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)

    # SQLAlchemy instrumentation hooks into the engine; importing the
    # engine here (rather than at module top) avoids the circular
    # `app.main → observability → db.session → app.main` chain.
    from app.db.session import engine

    SQLAlchemyInstrumentor().instrument(engine=engine)


def maybe_setup_profiling(settings: Settings) -> None:
    """Start the Pyroscope sampling thread when enabled.

    Wrapped in try/except so the dev image (which doesn't ship the
    optional ``pyroscope-io`` extra) only logs a warning instead of
    crashing on import. Per locked decision 5, this stays off in prod
    because gunicorn forks workers *after* import — the sampling thread
    would die in each child.
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
    )


# ---------------------------------------------------------------------------
# Per-request JSON access log
# ---------------------------------------------------------------------------


class AccessLogMiddleware:
    """ASGI middleware: emit one structured JSON log line per HTTP request.

    Lifts the per-request observability gap noted in ``setup_logging``'s
    docstring (W6 Phase 1 deferred the access log; the Repair Request Logs
    and Backend Logs With trace_id panels in dashboards 03 / 04 depend on
    it). OTel's FastAPI instrumentor wraps the entire middleware stack via
    a ``build_middleware_stack`` monkey-patch (not ``app.add_middleware``),
    so ``OpenTelemetryMiddleware`` ends up OUTSIDE every user middleware
    regardless of ``setup_*`` call order. The access log's ``finally``
    block therefore fires while the OTel span context is still attached,
    letting ``_structlog_processor_trace_context`` stamp ``trace_id`` /
    ``span_id`` onto the record — which in turn drives the Loki → Tempo
    derived-field link in Grafana. The invariant is pinned by
    ``tests/test_observability.py::test_access_log_runs_inside_otel_layer``.

    Logs flow through ``logging.getLogger("app.access")`` so structlog's
    stdlib bridge (configured in ``setup_logging``) renders them as JSON
    in prod and as key=value in dev — matching every other log line shape.

    Paths in :attr:`EXCLUDED_PATHS` are intentionally not logged. They are
    scrape / probe targets whose volume (Prometheus 15s, ECS / compose
    healthcheck ~10s, ALB target group similar) would dominate the log
    stream without carrying user-facing signal. Each is already covered by
    a dedicated metric: ``/metrics`` by the scrape itself, ``/health`` by
    the container's healthcheck state, ``/ready`` by the ALB target-group
    health.
    """

    EXCLUDED_PATHS: frozenset[str] = frozenset({"/metrics", "/health", "/ready"})

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        # structlog logger (not stdlib) so kwargs land directly in the
        # event_dict and survive the JSON renderer. stdlib ``extra={...}``
        # is silently dropped by ProcessorFormatter's foreign-record path
        # because no foreign_pre_chain processor lifts record attributes
        # into the dict — using structlog skips that gap entirely.
        self._logger = structlog.get_logger("app.access")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in self.EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        # Default to 500: if the downstream app raises before sending the
        # response start message, no http.response.start ever fires and we
        # still want a status_code in the access log. Starlette's exception
        # middleware will end up returning a 500 to the client in that
        # case, so the value matches what the user saw.
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            client = scope.get("client") or ("", 0)
            # Resolve the FastAPI route template (e.g.
            # ``/api/v1/repair-requests/{repair_request_id}/approve``) so
            # dashboards can group by handler without exploding cardinality
            # on the per-request raw path. Falls back to the raw path when
            # the request did not match a route (404 before routing).
            route = scope.get("route")
            route_template = getattr(route, "path", scope.get("path", ""))
            self._logger.info(
                "request",
                method=scope.get("method", ""),
                path=scope.get("path", ""),
                route=route_template,
                status_code=status_code,
                duration_ms=round(duration_ms, 2),
                client_ip=client[0] if client else "",
            )


def setup_access_log(app: FastAPI) -> None:
    """Attach :class:`AccessLogMiddleware`.

    OTel's FastAPI instrumentor wraps the entire stack via a
    ``build_middleware_stack`` monkey-patch, so this middleware's relative
    position vs ``setup_tracing`` is not load-bearing for ``trace_id``
    propagation. See the class docstring for the full rationale.
    """
    app.add_middleware(AccessLogMiddleware)
