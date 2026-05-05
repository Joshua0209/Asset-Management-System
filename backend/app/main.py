from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.schemas.repair_request import RepairRequestCreate

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        code = str(detail["code"])
        message = str(detail["message"])
        error_content: dict[str, object] = {"code": code, "message": message}
        if "details" in detail:
            error_content["details"] = detail["details"]
        content: dict[str, object] = {"error": error_content}
    else:
        code = _STATUS_CODE_MAP.get(exc.status_code, "error")
        message = detail if isinstance(detail, str) else code
        content = {"error": {"code": code, "message": message}}
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=getattr(exc, "headers", None),
    )


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
def health_check() -> dict[str, str]:
    return {"status": "ok"}
