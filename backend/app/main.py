import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.schemas.repair_request import RepairRequestCreate

logger = logging.getLogger(__name__)

settings = get_settings()

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
        # slowapi will inject X-RateLimit-* and Retry-After by way of
        # `_inject_headers` on the response we return; we still add a
        # conservative Retry-After fallback in case headers_enabled is off.
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
    """Liveness probe.

    Exempt from rate limiting so monitoring (compose healthcheck, ALB, etc.)
    cannot DoS itself when the global default tier shrinks.
    """
    return {"status": "ok"}
