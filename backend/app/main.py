from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings

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
    422: "validation_error",
    429: "rate_limit_exceeded",
    503: "service_unavailable",
}


@app.exception_handler(HTTPException)
async def http_exception_to_envelope(request: Request, exc: HTTPException) -> JSONResponse:
    """Rewrap FastAPI HTTPException into the project's error envelope."""
    code = _STATUS_CODE_MAP.get(exc.status_code, "error")
    message = exc.detail if isinstance(exc.detail, str) else code
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message}},
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


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
