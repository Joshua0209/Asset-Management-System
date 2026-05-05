from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models.repair_image import RepairImage
from app.models.repair_request import RepairRequest
from app.schemas.common import UUID_PATTERN, ErrorResponse
from app.services.image_storage import (
    ImageStorageDep,
    ImageStorageError,
    image_storage_error_to_http,
)

logger = logging.getLogger(__name__)
router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]
ImageIdPath = Annotated[
    str,
    Path(pattern=UUID_PATTERN, json_schema_extra={"format": "uuid"}),
]

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}


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
