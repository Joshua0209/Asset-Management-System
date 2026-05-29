from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.repair_image import RepairImage
from app.models.repair_request import RepairRequest
from app.models.user import UserRole
from app.schemas.common import UUIDPath, error_responses
from app.services.image_storage import (
    ImageStorageDep,
    ImageStorageError,
    image_storage_error_to_http,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _image_rate_limit() -> str:
    """Return the current image-tier limit string.

    Lazy callable form (vs ``@limiter.limit(<str>)``) so the value is
    re-read per request and tests that toggle env vars don't have to
    work around an import-time string baked into the decorator.
    """
    return get_settings().rate_limit_images


DbSession = Annotated[Session, Depends(get_db)]
ImageIdPath = UUIDPath

# 500 covers ImageStorageIntegrityError (corrupted DB row → permanent error).
_ERROR_RESPONSES = error_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_422_UNPROCESSABLE_ENTITY,
    status.HTTP_429_TOO_MANY_REQUESTS,
    status.HTTP_500_INTERNAL_SERVER_ERROR,
    status.HTTP_503_SERVICE_UNAVAILABLE,
)


@router.get(
    "/{image_id}",
    summary="Retrieve repair image",
    response_class=Response,
    responses={
        status.HTTP_200_OK: {
            "description": "Binary repair image.",
            "headers": {
                "Cache-Control": {
                    "schema": {"type": "string"},
                    "example": "private, max-age=3600",
                }
            },
            "content": {
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                "image/png": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        **_ERROR_RESPONSES,
    },
)
@limiter.limit(_image_rate_limit)
def get_image(
    request: Request,
    image_id: ImageIdPath,
    db: DbSession,
    current_user: CurrentUser,
    storage: ImageStorageDep,
) -> Response:
    # Object-level authorization (issue #123 / OWASP API1:2023): a holder may
    # only fetch images attached to their own repair requests; managers retain
    # full access. The ownership predicate is folded into the WHERE clause so a
    # non-owning holder yields no row → the shared 404 branch below, which does
    # not confirm the image's existence (preferred over 403). This mirrors the
    # requester_id filter on GET /repair-requests and its 403 on the parent.
    try:
        stmt = (
            select(RepairImage)
            .join(RepairRequest, RepairImage.repair_request_id == RepairRequest.id)
            .where(
                RepairImage.id == image_id,
                RepairRequest.deleted_at.is_(None),
            )
        )
        if current_user.role is UserRole.HOLDER:
            stmt = stmt.where(RepairRequest.requester_id == current_user.id)
        image = db.scalar(stmt)
    except SQLAlchemyError as exc:
        logger.exception("Failed to load image %s", image_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve image. Please try again later.",
        ) from exc

    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")

    try:
        content, content_type = storage.open(image.image_url)
    except ImageStorageError as exc:
        logger.warning("Image %s storage read failed: %s", image_id, exc)
        raise image_storage_error_to_http(exc) from exc

    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )
