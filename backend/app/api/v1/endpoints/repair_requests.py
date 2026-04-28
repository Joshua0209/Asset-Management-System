import logging
import math
import re
import uuid
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.orm.interfaces import ORMOption

from app.api.deps import CurrentUser, HolderUser
from app.core.config import get_settings
from app.db.session import get_db
from app.models.asset import Asset, AssetStatus
from app.models.repair_image import RepairImage
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import UserRole
from app.schemas.common import DataResponse, PaginatedListResponse, PaginationMeta
from app.schemas.repair_request import RepairRequestCreate, RepairRequestRead

logger = logging.getLogger(__name__)
router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]

_ACTIVE_REPAIR_STATUSES = {
    RepairRequestStatus.PENDING_REVIEW,
    RepairRequestStatus.UNDER_REPAIR,
}
_SORT_COLUMNS = {
    "created_at": RepairRequest.created_at,
    "status": RepairRequest.status,
}
_ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
_MAX_IMAGE_COUNT = 5
_MAX_IMAGE_BYTES = 5 * 1024 * 1024


class SubmittedImage:
    def __init__(self, *, filename: str, content_type: str, content: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self.content = content


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _validation_error(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message)


def _base_filters() -> list[ColumnElement[bool]]:
    return [RepairRequest.deleted_at.is_(None)]


def _repair_options() -> tuple[ORMOption, ...]:
    return (
        joinedload(RepairRequest.asset),
        joinedload(RepairRequest.requester),
        joinedload(RepairRequest.reviewer),
        joinedload(RepairRequest.images),
    )


def _parse_content_disposition(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in value.split(";")[1:]:
        if "=" not in part:
            continue
        key, raw_value = part.strip().split("=", maxsplit=1)
        result[key] = raw_value.strip('"')
    return result


def _parse_multipart_fields(
    content_type: str,
    body: bytes,
) -> tuple[dict[str, str], list[SubmittedImage]]:
    boundary_match = re.search(r"boundary=([^;]+)", content_type)
    if boundary_match is None:
        raise _validation_error("multipart boundary is required.")
    boundary_value = boundary_match.group(1).strip().strip('"')
    boundary = f"--{boundary_value}".encode()
    fields: dict[str, str] = {}
    images: list[SubmittedImage] = []
    for raw_part in body.split(boundary):
        part = raw_part.strip()
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].strip()
        if b"\r\n\r\n" not in part:
            continue
        raw_headers, content = part.split(b"\r\n\r\n", maxsplit=1)
        headers: dict[str, str] = {}
        for header_line in raw_headers.decode(errors="ignore").split("\r\n"):
            if ":" not in header_line:
                continue
            key, value = header_line.split(":", maxsplit=1)
            headers[key.lower()] = value.strip()
        disposition = _parse_content_disposition(headers.get("content-disposition", ""))
        name = disposition.get("name")
        if name is None:
            continue
        content = content.removesuffix(b"\r\n")
        if disposition.get("filename") is not None:
            if name == "images":
                images.append(
                    SubmittedImage(
                        filename=disposition.get("filename", ""),
                        content_type=headers.get("content-type", ""),
                        content=content,
                    )
                )
            continue
        fields[name] = content.decode(errors="ignore")
    return fields, images


def _validate_images(images: list[SubmittedImage]) -> None:
    if len(images) > _MAX_IMAGE_COUNT:
        raise _validation_error("At most 5 images may be uploaded.")
    for image in images:
        if image.content_type not in _ALLOWED_IMAGE_TYPES:
            raise _validation_error("Images must be JPEG or PNG.")
        if len(image.content) > _MAX_IMAGE_BYTES:
            raise _validation_error("Each image must be 5 MB or smaller.")


def _persist_images(repair_request: RepairRequest, images: list[SubmittedImage]) -> None:
    if not images:
        return
    upload_root = Path(get_settings().repair_upload_dir)
    request_dir = upload_root / repair_request.id
    request_dir.mkdir(parents=True, exist_ok=True)
    for image in images:
        image_id = str(uuid.uuid4())
        suffix = _ALLOWED_IMAGE_TYPES[image.content_type]
        target = request_dir / f"{image_id}{suffix}"
        target.write_bytes(image.content)
        repair_request.images.append(
            RepairImage(
                id=image_id,
                repair_request_id=repair_request.id,
                image_url=f"/uploads/repair-requests/{repair_request.id}/{target.name}",
            )
        )


async def _repair_payload_from_request(
    request: Request,
) -> tuple[RepairRequestCreate, list[SubmittedImage]]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        raw_payload = await request.json()
        return RepairRequestCreate.model_validate(raw_payload), []

    body = await request.body()
    if content_type.startswith("multipart/form-data"):
        fields, images = _parse_multipart_fields(content_type, body)
        _validate_images(images)
        return RepairRequestCreate.model_validate(fields), images

    parsed = parse_qs(body.decode(), keep_blank_values=True)
    fields = {key: values[-1] if values else "" for key, values in parsed.items()}
    return RepairRequestCreate.model_validate(fields), []


@router.get("", summary="List repair requests")
def list_repair_requests(
    db: DbSession,
    current_user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[RepairRequestStatus | None, Query(alias="status")] = None,
    asset_id: str | None = None,
    requester_id: str | None = None,
    sort: str = "-created_at",
) -> PaginatedListResponse[RepairRequestRead]:
    try:
        filters = _base_filters()
        if status_filter is not None:
            filters.append(RepairRequest.status == status_filter)
        if asset_id:
            filters.append(RepairRequest.asset_id == asset_id)
        if current_user.role is UserRole.HOLDER:
            if requester_id is not None and requester_id != current_user.id:
                raise _forbidden("Holder users can only list their own repair requests.")
            filters.append(RepairRequest.requester_id == current_user.id)
        elif requester_id:
            filters.append(RepairRequest.requester_id == requester_id)

        sort_desc = sort.startswith("-")
        sort_field = sort[1:] if sort_desc else sort
        sort_column = _SORT_COLUMNS.get(sort_field)
        if sort_column is None:
            raise _validation_error("Unsupported repair request sort field.")
        order_by = sort_column.desc() if sort_desc else sort_column.asc()

        total = db.scalar(select(func.count()).select_from(RepairRequest).where(*filters)) or 0
        requests = db.scalars(
            select(RepairRequest)
            .options(*_repair_options())
            .where(*filters)
            .order_by(order_by)
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).unique().all()
        return PaginatedListResponse(
            data=[RepairRequestRead.model_validate(item) for item in requests],
            meta=PaginationMeta(
                total=total,
                page=page,
                per_page=per_page,
                total_pages=math.ceil(total / per_page) if total else 0,
            ),
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.error("Failed to list repair requests: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve repair requests. Please try again later.",
        ) from exc


@router.post("", status_code=status.HTTP_201_CREATED, summary="Submit repair request")
async def submit_repair_request(
    request: Request,
    db: DbSession,
    response: Response,
    current_user: HolderUser,
) -> DataResponse[RepairRequestRead]:
    try:
        payload, images = await _repair_payload_from_request(request)
        asset = db.scalar(
            select(Asset).where(Asset.id == payload.asset_id, Asset.deleted_at.is_(None))
        )
        if asset is None:
            raise _not_found("Asset not found.")
        if asset.responsible_person_id != current_user.id:
            raise _forbidden("Requester is not assigned to this asset.")
        if payload.version is not None and asset.version != payload.version:
            raise _conflict("Asset was modified by another user. Please refresh and try again.")
        if asset.status is not AssetStatus.IN_USE:
            raise _conflict("Repair request is only allowed for assets in use.")

        active_count = db.scalar(
            select(func.count())
            .select_from(RepairRequest)
            .where(
                RepairRequest.asset_id == asset.id,
                RepairRequest.deleted_at.is_(None),
                RepairRequest.status.in_(_ACTIVE_REPAIR_STATUSES),
            )
        )
        if active_count:
            raise _conflict("Repair request already exists for this asset.")

        repair_request = RepairRequest(
            asset_id=asset.id,
            requester_id=current_user.id,
            status=RepairRequestStatus.PENDING_REVIEW,
            fault_description=payload.fault_description,
        )
        repair_request.asset = asset
        repair_request.requester = current_user
        asset.status = AssetStatus.PENDING_REPAIR
        db.add(repair_request)
        db.flush()
        _persist_images(repair_request, images)
        db.flush()
        response.headers["Location"] = f"/api/v1/repair-requests/{repair_request.id}"
        result = DataResponse(data=RepairRequestRead.model_validate(repair_request))
        db.commit()
        return result
    except HTTPException:
        raise
    except StaleDataError as exc:
        db.rollback()
        logger.warning("Repair request submit conflict: %s", exc)
        raise _conflict(
            "Asset was modified by another user. Please refresh and try again."
        ) from exc
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Repair request submit constraint error: %s", exc)
        raise _conflict(
            "Repair request could not be submitted due to a conflicting state."
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to submit repair request: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to submit repair request. Please try again later.",
        ) from exc
