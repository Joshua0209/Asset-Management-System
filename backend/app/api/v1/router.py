from fastapi import APIRouter

from app.api.v1.endpoints import assets, auth, images, repair_requests, users

# CORS surface invariants — the defaults in `Settings.cors_allowed_methods`
# and `Settings.cors_allowed_headers` are tightly scoped to the actual route
# verbs and request headers below. If you add either of:
#
#   * a `@router.delete(...)` route on any router below, OR
#   * code that reads/sends an `If-Match` header,
#
# you MUST broaden `CORS_ALLOWED_METHODS` / `CORS_ALLOWED_HEADERS` (env var
# override, not source change) in every environment that serves real traffic.
# See docs/system-design/08-deployment-operations.md §"CORS Allowlist".
api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(
    repair_requests.router,
    prefix="/repair-requests",
    tags=["repair_requests"],
)
api_router.include_router(images.router, prefix="/images", tags=["images"])
