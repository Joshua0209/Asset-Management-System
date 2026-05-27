import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.observability import (
    FRONTEND_OBS_BEACON_RATE_LIMITED,
    maybe_setup_profiling,
    setup_access_log,
    setup_log_exporter,
    setup_logging,
    setup_metrics,
    setup_metrics_exporter,
    setup_tracing,
    verify_observability_exports,
)
from app.core.rate_limit import limiter
from app.db.session import engine
from app.schemas.repair_request import RepairRequestCreate

settings = get_settings()

# Configure structlog AND attach the OTel log exporter BEFORE any
# logger.warning() below so the boot-time rate-limit / proxy-trust
# warnings (and the single-worker guard's RuntimeError chain) land in
# Grafana Cloud Loki as structured records, not pre-config plaintext on
# the container stderr where only CloudWatch can find them. The exporter
# is a no-op when OTEL_ENABLED is false (pytest / dev default), so this
# is safe for non-prod boots too. Idempotent for re-imports under pytest.
setup_logging(settings)
setup_log_exporter(settings)

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

if not settings.rate_limit_enabled:
    # Loud-on-misconfig: a deploy with RATE_LIMIT_ENABLED=false is
    # almost certainly a leaked test fixture, not an intentional
    # production switch. Logged as WARNING (not just INFO) so it
    # surfaces in CloudWatch's default Lambda Insights / ECS log
    # filters. CLAUDE.md "no silent failures" — startup is the loudest
    # place we can put this.
    logger.warning(
        "Rate limiting is DISABLED (RATE_LIMIT_ENABLED=false). "
        "This must only be set in tests; production deploys MUST "
        "leave it true to avoid credential-stuffing exposure on "
        "/auth/login + /auth/register."
    )


def _enforce_single_worker_invariant(
    settings_obj: "object",
    web_concurrency_raw: str | None,
    gunicorn_workers_raw: str | None = None,
) -> None:
    """Refuse to boot when multi-worker would silently relax rate limits.

    Per ``docs/system-design/08-deployment-operations.md`` §"API Hardening:
    Rate Limiting", Phase 2 mandates ``--workers 1`` until Phase 3 introduces
    Redis-backed shared storage. Slowapi's ``MemoryStorage`` is per-process,
    so N workers means a user's effective per-minute cap is N× the configured
    value — credential-stuffing protection on ``/auth/login`` is silently
    defeated. We refuse to start rather than serve traffic with that hole.

    Two env-var conventions are checked because the Dockerfile / task-def
    layers used both at different times:

    * ``WEB_CONCURRENCY`` — tiangolo / ``uvicorn-gunicorn-fastapi`` convention.
    * ``GUNICORN_WORKERS`` — the variable name this repo's ``Dockerfile.prod``
      historically baked into ``--workers ${GUNICORN_WORKERS}``. The new
      image switches to ``WEB_CONCURRENCY``, but a stale ECS task definition
      in the wild may still set ``GUNICORN_WORKERS`` — the invariant must
      catch it either way.

    Known gap: ``uvicorn --workers N`` CLI flag is NOT readable from inside
    the app (uvicorn does not export it to the process environment). The
    runbook in ``08-deployment-operations.md`` carries the verbal "use
    ``--workers 1``" mandate; this function backstops the env-var shape only.

    Malformed values (``""``, ``"auto"``, non-numeric) degrade to single-worker
    rather than raising ``ValueError`` — a confusing crash for an operator who
    set a stray value is worse than treating it as "unset".
    """
    if not getattr(settings_obj, "rate_limit_enabled", True):
        # Rate limiting off → the N-worker concern is moot. The existing
        # WARN above already flags the disabled state loudly.
        return

    def _parse(raw: str | None) -> int:
        if raw is None:
            return 1
        try:
            value = int(raw.strip())
        except (ValueError, AttributeError):
            # Garbled env value → treat as unset. Operator gets no false
            # alarm, and the surrounding gunicorn/uvicorn layer will
            # surface the bad value on its own when it tries to spawn
            # processes.
            return 1
        return value if value > 0 else 1

    web_workers = _parse(web_concurrency_raw)
    gunicorn_workers = _parse(gunicorn_workers_raw)
    effective = max(web_workers, gunicorn_workers)
    if effective <= 1:
        return

    offenders = []
    if web_workers > 1:
        offenders.append(f"WEB_CONCURRENCY={web_workers}")
    if gunicorn_workers > 1:
        offenders.append(f"GUNICORN_WORKERS={gunicorn_workers}")
    offender_str = " and ".join(offenders)

    raise RuntimeError(
        f"{offender_str} but rate-limit storage is in-process MemoryStorage. "
        f"Effective per-user/per-IP cap is {effective}x the configured value, "
        "which silently defeats credential-stuffing protection on /auth/login. "
        "Per docs/system-design/08-deployment-operations.md, keep --workers 1 "
        "until Phase 3 introduces Redis-backed shared storage. Set "
        "WEB_CONCURRENCY=1 and GUNICORN_WORKERS=1 (or unset both) to boot. "
        "To intentionally bypass for load tests, set RATE_LIMIT_ENABLED=false."
    )


_enforce_single_worker_invariant(
    settings,
    os.environ.get("WEB_CONCURRENCY"),
    os.environ.get("GUNICORN_WORKERS"),
)


def _warn_if_proxy_trust_misconfigured(
    settings_obj: "object", forwarded_allow_ips_raw: str | None
) -> None:
    """WARN when ``FORWARDED_ALLOW_IPS`` is the loopback default in production.

    The prod image's default is ``127.0.0.1`` so local prod-image runs match
    uvicorn's own default. Behind the ALB, the immediate TCP peer is the
    load-balancer's private IP — NOT the loopback — so uvicorn's
    ``ProxyHeadersMiddleware`` refuses to rewrite ``request.client.host`` from
    ``X-Forwarded-For``. Every anonymous request then collapses into one
    bucket keyed on the ALB IP, and the limiter silently self-DoSes.

    The fix is to set ``FORWARDED_ALLOW_IPS=*`` in the ECS task definition,
    which is safe so long as the task security group restricts ingress to
    the ALB (the SG, not ``*``, is what enforces ALB-only traffic — see
    ``docs/system-design/08-deployment-operations.md`` §"Behind the ALB").
    This WARN gives operators a CloudWatch breadcrumb when the override is
    missing — mirroring the existing ``RATE_LIMIT_ENABLED=false`` WARN.

    Skipped when rate limiting is off, since the rate-limit-disabled WARN
    already covers that case loudly.
    """
    if not getattr(settings_obj, "rate_limit_enabled", True):
        return
    if forwarded_allow_ips_raw is None or forwarded_allow_ips_raw.strip() == "127.0.0.1":
        logger.warning(
            "FORWARDED_ALLOW_IPS is unset or 127.0.0.1 while rate limiting is "
            "enabled. Behind an ALB this collapses every anonymous request "
            "into the load-balancer's private-IP bucket and silently defeats "
            "credential-stuffing protection on /auth/login. Set "
            "FORWARDED_ALLOW_IPS in the ECS task definition. See "
            "docs/system-design/08-deployment-operations.md §'Behind the ALB: "
            "client-IP resolution' for the value to use and the SG-ingress "
            "precondition that keeps it safe."
        )


_warn_if_proxy_trust_misconfigured(settings, os.environ.get("FORWARDED_ALLOW_IPS"))


def _warn_if_database_config_is_legacy(settings_obj: "object") -> None:
    """WARN when the legacy ``DB_HOST``/``DB_NAME``/``DB_USER``/``DB_PASSWORD`` set is in use.

    Per ``backend/app/core/config.py``, the canonical production path is a
    single ``DATABASE_URL`` (typically resolved from Secrets Manager via
    ``DATABASE_URL_SECRET_NAME`` in the ECS task definition). The
    component-parts form is retained only for legacy local setups that
    predate the migration. Without a startup signal an operator cannot
    tell from outside the container which path is in use, so a botched
    Secrets Manager fetch that silently fell through to the component
    defaults would never be visible until the next config audit.

    Logged as WARNING (not INFO) so it surfaces in CloudWatch's default
    log-level filters — mirrors the posture of the rate-limit-disabled
    and FORWARDED_ALLOW_IPS warnings above.
    """
    if getattr(settings_obj, "database_url", None):
        return
    logger.warning(
        "Database configured via legacy DB_HOST/DB_NAME/DB_USER/DB_PASSWORD "
        "env vars, not DATABASE_URL. Production deploys should pull a single "
        "DATABASE_URL from Secrets Manager via DATABASE_URL_SECRET_NAME (see "
        "infra/aws/tasks/backend-task-def.json). The component-parts form remains "
        "supported for legacy local setups only."
    )


_warn_if_database_config_is_legacy(settings)

# slowapi expects the limiter on app.state; SlowAPIMiddleware reads it at
# request time and emits the X-RateLimit-* headers.
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=settings.cors_allowed_methods,
    allow_headers=settings.cors_allowed_headers,
)

# Observability (W6 Phase 3, OTLP-native):
#   Ordering after setup_logging + setup_log_exporter (above):
#   metrics_exporter → metrics → tracing → profiling → access_log.
#
#   setup_metrics_exporter MUST run before setup_metrics: the FastAPI
#   instrumentor's ``instrument_app`` resolves ``get_meter()`` at call
#   time, and creates HTTP server instruments (request duration
#   histogram, request counter, etc.) at that moment. Current OTel
#   1.27 ``_ProxyMeter`` rebinds those instruments when a real
#   provider is set later, so the previous reversed order happened to
#   work — but it depended on a documented-but-fragile SDK internal.
#   A future SDK that switches to eager binding (or a third-party
#   instrumentor that caches its meter reference) would silently stop
#   publishing HTTP server metrics, and the metric-renaming Views
#   installed in setup_metrics_exporter would never apply to the
#   instrumentor's instruments. Installing the real provider first
#   makes the binding direct, no proxy hop.
#
#   setup_metrics still must run before app startup so the ASGI
#   middleware is registered (FastAPI rejects middleware added after
#   startup). Every setup_* is a no-op when OTEL_ENABLED=false
#   (pytest default), so the suite stays free of OTLP exporter
#   threads.
#
#   maybe_setup_profiling is gated by PYROSCOPE_ENABLED (production
#   sets it true). The ``WEB_CONCURRENCY=1`` invariant above plus no
#   ``gunicorn --preload`` means the sampling thread starts inside
#   the worker post-fork.
#
#   setup_access_log registers AccessLogMiddleware so every request emits
#   a structured JSON log line tagged with route + status + duration +
#   trace_id. OTel's FastAPI instrumentor wraps the entire stack via a
#   ``build_middleware_stack`` monkey-patch, so this call's position
#   relative to ``setup_tracing`` is not load-bearing for trace_id
#   propagation; the access log always runs INSIDE the OTel span context.
#   Pinned by tests/test_observability.py::test_access_log_runs_inside_otel_layer.
setup_metrics_exporter(settings)
setup_metrics(app, settings)
setup_tracing(settings)
maybe_setup_profiling(settings)
setup_access_log(app)
# Fail-fast smoke test: in non-local envs, refuse to boot if any OTLP
# provider's force_flush returns False. Closes the silent-export-failure
# gap where a wrong API key would otherwise drop every span/metric/log
# while the container reports healthy to the ALB.
verify_observability_exports(settings)

# Map HTTP status → machine-readable error code per docs/system-design/12-api-design.md
_STATUS_CODE_MAP = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limit_exceeded",
    500: "internal_server_error",
    503: "service_unavailable",
}


@app.exception_handler(HTTPException)
async def http_exception_to_envelope(request: Request, exc: HTTPException) -> JSONResponse:
    """Rewrap FastAPI HTTPException into the project's error envelope.

    Endpoints can pass a structured `detail={"code": ..., "message": ...}` to
    pick a granular `error.code` within a single status (e.g. distinguishing
    `duplicate_request` / `invalid_transition` / `conflict` for 409 per
    `docs/system-design/12-api-design.md`). Otherwise the status-code map
    selects the code and `detail` becomes the message.
    """
    detail = exc.detail
    default_code = _STATUS_CODE_MAP.get(exc.status_code, "error")
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        code = str(detail["code"])
        message = str(detail["message"])
        error_content: dict[str, object] = {"code": code, "message": message}
        if "details" in detail:
            error_content["details"] = detail["details"]
        content: dict[str, object] = {"error": error_content}
    else:
        if isinstance(detail, dict):
            # Half-built structured detail is a developer bug (silent-failure
            # risk per past review). Log it so it shows up in observability
            # instead of silently degrading; then fall back to the status-map
            # default so we never leak the raw dict into `error.message`.
            logger.warning(
                "HTTPException detail dict missing 'code' or 'message'; "
                "falling back to status-map default. detail=%s",
                detail,
            )
        code = default_code
        message = detail if isinstance(detail, str) else default_code
        content = {"error": {"code": code, "message": message}}
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_to_envelope(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Catch Pydantic ``ValidationError`` that escapes route boundaries.

    FastAPI's :class:`RequestValidationError` covers request-binding failures.
    Anything else (e.g. ``Schema.model_validate(...)`` raising on internal
    data drift) lands here. These indicate programmer / data bugs, not user
    input — log and surface a generic 500 in the project's error envelope so
    we never leak unstructured FastAPI defaults.
    """
    logger.error("Internal pydantic ValidationError: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_server_error",
                "message": "Internal validation error.",
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_to_envelope(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all so non-HTTPException failures still emit the project envelope.

    Without this, Starlette's default returns ``{"detail": "Internal Server Error"}``
    which silently violates the response contract (`docs/system-design/12-api-design.md`).
    """
    logger.error(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_server_error",
                "message": "Internal server error.",
            }
        },
    )


def register_rate_limit_handler(target_app: FastAPI) -> None:
    """Attach a RateLimitExceeded → project error envelope handler.

    Extracted so test apps can register the same handler without re-importing
    the whole production app. slowapi's default handler returns
    ``{"error": "Rate limit exceeded"}`` which would break the FE's contract
    that every error follows ``{"error": {"code": ..., "message": ...}}``.

    Important: slowapi's SlowAPIMiddleware looks up this handler via
    ``app.exception_handlers[RateLimitExceeded]`` *synchronously* (see
    ``slowapi.middleware.sync_check_limits``). If the registered handler is a
    coroutine the middleware silently falls back to slowapi's default body,
    so this MUST stay a plain ``def``.
    """

    @target_app.exception_handler(RateLimitExceeded)
    def _rate_limit_to_envelope(
        request: Request, exc: RateLimitExceeded
    ) -> JSONResponse:
        # `exc.detail` is e.g. "3 per 1 minute" — surface it as the message
        # so clients can show the configured limit without leaking internals.
        message = f"Rate limit exceeded: {exc.detail}"
        # The beacon endpoint is fire-and-forget; the browser cannot read
        # this 429. Tick a dedicated counter so the truncation itself is
        # alertable, otherwise FRONTEND_OBS_FAILURES silently under-counts
        # during a failure storm. Match on the path suffix so the prefix
        # (api_v1_prefix) can change without touching this handler.
        if request.url.path.endswith("/observability/client-error"):
            FRONTEND_OBS_BEACON_RATE_LIMITED.add(1)
        # SlowAPIMiddleware injects X-RateLimit-* on the response on its way
        # back through the stack when `headers_enabled=True`. We seed
        # Retry-After defensively here so a misconfigured limiter
        # (`headers_enabled=False`) still gives clients a usable backoff
        # signal — slowapi will overwrite it when it does fire.
        headers = dict(getattr(exc, "headers", None) or {})
        headers.setdefault("Retry-After", "60")
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": message,
                }
            },
            headers=headers,
        )


register_rate_limit_handler(app)


@app.exception_handler(RequestValidationError)
async def validation_error_to_envelope(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Rewrap Pydantic/FastAPI validation failures into the error envelope.

    Per docs/system-design/12-api-design.md, 422 responses carry
    `error.code = "validation_error"` and a `details` array of field-level errors.
    The first element of Pydantic's `loc` tuple identifies the request part
    (body/query/path) and is stripped so `field` stays user-facing.
    """
    details = [
        {
            "field": ".".join(str(part) for part in err.get("loc", ())[1:]),
            "message": err.get("msg", ""),
            "code": err.get("type", "value_error"),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Validation failed",
                "details": details,
            }
        },
    )


app.include_router(api_router, prefix=settings.api_v1_prefix)


def custom_openapi() -> dict[str, object]:
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    schemas = openapi_schema.setdefault("components", {}).setdefault("schemas", {})
    schemas["RepairRequestCreate"] = RepairRequestCreate.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]


@app.get("/health", tags=["health"])
@limiter.exempt  # type: ignore[untyped-decorator]  # slowapi decorators have no type stubs
def health_check(request: Request) -> dict[str, str]:
    """Liveness probe — process is up. Used by ECS task health and `docker compose`.

    Exempt from rate limiting so monitoring (compose healthcheck, ALB, etc.)
    cannot DoS itself when the global default tier shrinks.
    """
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
@limiter.exempt  # type: ignore[untyped-decorator]  # readiness probes must not consume app quota
def readiness_check() -> JSONResponse:
    """Readiness probe — process can serve traffic (DB reachable).

    ALB target groups should hit this; returning 503 lets the load balancer
    drain a target whose DB connection has dropped (e.g. RDS Multi-AZ
    failover in progress) without killing the container itself.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — see comment block below
        # Broad ``except`` is the right shape for a *probe* (in contrast
        # to business logic where it would mask bugs). Three real
        # failure modes the prior ``SQLAlchemyError``-only catch missed:
        #
        # 1. ``QueuePool``/``TimeoutError`` on pool exhaustion: derives
        #    from ``Exception``, not ``SQLAlchemyError``. The container
        #    would 500 instead of 503, ALB would kill the task instead
        #    of draining the unhealthy target.
        # 2. ``OSError`` / ``ConnectionRefusedError`` from the DB driver
        #    layer (RDS Multi-AZ failover mid-probe) that the SQLAlchemy
        #    wrapper sometimes lets through directly.
        # 3. Any third-party driver / instrumentation that raises a
        #    non-SQLAlchemy exception type (e.g. OTel SQLAlchemy
        #    instrumentor edge cases under partial-shutdown).
        #
        # A readiness probe that 5xx's on an unexpected exception type
        # is strictly worse than one that 503's: 503 lets ALB drain
        # the target without killing the otherwise-fine container; 5xx
        # gets retried by the ALB and may trip the deploy gate. Catch
        # broadly here on purpose.
        logger.warning("Readiness probe failed: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": {"database": "down"}},
        )
    return JSONResponse(
        status_code=200,
        content={"status": "ready", "checks": {"database": "up"}},
    )
