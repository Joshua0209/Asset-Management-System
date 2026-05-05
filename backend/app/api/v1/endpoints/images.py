from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models.repair_image import RepairImage
from app.models.repair_request import RepairRequest
from app.schemas.common import UUIDPath, error_responses
from app.services.image_storage import (
    ImageStorageDep,
    ImageStorageError,
    image_storage_error_to_http,
)

logger = logging.getLogger(__name__)
router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]
ImageIdPath = UUIDPath

# 500 covers ImageStorageIntegrityError (corrupted DB row → permanent error).
_ERROR_RESPONSES = error_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_422_UNPROCESSABLE_ENTITY,
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
def get_image(
    image_id: ImageIdPath,
    db: DbSession,
    # Auth required, identity unused.
    current_user: CurrentUser,  # noqa: ARG001
    storage: ImageStorageDep,
) -> Response:
    try:
        image = db.scalar(
            select(RepairImage)
            .join(RepairRequest, RepairImage.repair_request_id == RepairRequest.id)
            .where(
                RepairImage.id == image_id,
                RepairRequest.deleted_at.is_(None),
            )
        )
    except SQLAlchemyError as exc:
        logger.error("Failed to load image %s: %s", image_id, exc, exc_info=True)
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
