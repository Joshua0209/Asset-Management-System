from fastapi import APIRouter

from app.api.v1.endpoints import assets, auth, repair_requests, users

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(
    repair_requests.router,
    prefix="/repair-requests",
    tags=["repair_requests"],
)
