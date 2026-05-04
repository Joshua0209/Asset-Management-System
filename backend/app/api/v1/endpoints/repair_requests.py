import logging
import math
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, cast
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.exc import (
    DataError,
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
)
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.orm.interfaces import ORMOption

from app.api.deps import CurrentUser, HolderUser, ManagerUser
from app.core.config import get_settings
from app.db.session import get_db
from app.models.asset import Asset, AssetStatus
from app.models.repair_image import RepairImage
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import UserRole
from app.schemas.common import DataResponse, PaginatedListResponse, PaginationMeta
from app.schemas.repair_request import (
    RepairRequestApprove,
    RepairRequestComplete,
    RepairRequestCreate,
    RepairRequestDetailsUpdate,
    RepairRequestRead,
    RepairRequestReject,
)
from app.services.image_storage import ImageStorageDep

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
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_START = b"\xff\xd8"
_JPEG_END = b"\xff\xd9"
_MAX_IMAGE_COUNT = 5
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_MAX_IMAGE_MEGABYTES = _MAX_IMAGE_BYTES // (1024 * 1024)
_MULTIPART_OVERHEAD_BYTES = 64 * 1024
_MAX_REQUEST_BYTES = _MAX_IMAGE_COUNT * _MAX_IMAGE_BYTES + _MULTIPART_OVERHEAD_BYTES

# Whitelist of fields that update_repair_details may forward to the ORM via
# setattr. Guards against silent schema/model drift if the schema gains a
# field that does not exist on RepairRequest.
_REPAIR_DETAILS_UPDATABLE_FIELDS = frozenset({
    "repair_date",
    "fault_content",
    "repair_plan",
    "repair_cost",
    "repair_vendor",
})


@dataclass(frozen=True, kw_only=True)
class SubmittedImage:
    filename: str
    content_type: str
    content: bytes


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


def _repair_query() -> Select[tuple[RepairRequest]]:
    return select(RepairRequest).options(*_repair_options())


def _get_repair_request(db: Session, repair_request_id: str) -> RepairRequest:
    repair_request = db.scalar(
        _repair_query().where(
            RepairRequest.id == repair_request_id,
            RepairRequest.deleted_at.is_(None),
        )
    )
    if repair_request is None:
        raise _not_found("Repair request not found.")
    return repair_request


def _ensure_request_version(repair_request: RepairRequest, version: int) -> None:
    if repair_request.version != version:
        raise _conflict(
            "Repair request was modified by another user. Please refresh and try again."
        )


def _ensure_asset_status(
    repair_request: RepairRequest,
    expected_status: AssetStatus,
    message: str,
) -> Asset:
    asset = repair_request.asset
    if asset is None:
        # asset_id is a NOT NULL FK with ondelete=CASCADE; reaching this branch
        # means schema integrity is broken, not that the user gave a bad URL.
        logger.error(
            "Repair request %s has no associated asset (data integrity error)",
            repair_request.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal data integrity error.",
        )
    if asset.deleted_at is not None:
        logger.warning(
            "Repair request %s references soft-deleted asset %s",
            repair_request.id,
            asset.id,
        )
        raise _conflict(
            "Associated asset has been deleted; repair request cannot proceed."
        )
    if asset.status is not expected_status:
        raise _conflict(message)
    return cast(Asset, asset)


def _ensure_request_status(
    repair_request: RepairRequest,
    expected_status: RepairRequestStatus,
    message: str,
) -> None:
    if repair_request.status is not expected_status:
        raise _conflict(message)


def _commit_repair_change(
    db: Session,
    repair_request: RepairRequest,
    log_context: str,
) -> DataResponse[RepairRequestRead]:
    try:
        db.commit()
        db.refresh(repair_request)
        return DataResponse(data=RepairRequestRead.model_validate(repair_request))
    except StaleDataError as exc:
        db.rollback()
        logger.warning("%s conflict: %s", log_context, exc)
        raise _conflict(
            "Repair request was modified by another user. Please refresh and try again."
        ) from exc
    except OperationalError as exc:
        # Connection lost, deadlock, lock timeout — caller may retry.
        db.rollback()
        logger.error("%s transient DB error: %s", log_context, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to update repair request. Please try again later.",
        ) from exc
    except IntegrityError as exc:
        # FK / unique / NOT NULL / check-constraint violation — surfaces a
        # state conflict that retrying will not resolve.
        db.rollback()
        logger.warning("%s integrity error: %s", log_context, exc)
        raise _conflict(
            "Repair request could not be updated due to a conflicting state."
        ) from exc
    except DataError as exc:
        # Value out of range / invalid enum / oversize column — caller's input.
        db.rollback()
        logger.warning("%s data error: %s", log_context, exc)
        raise _validation_error(
            "Repair request payload contains invalid values."
        ) from exc
    except SQLAlchemyError as exc:
        # ProgrammingError / InvalidRequestError / unknown — programmer bug.
        db.rollback()
        logger.error("%s unexpected DB error: %s", log_context, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal database error.",
        ) from exc


def _parse_content_disposition(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in value.split(";")[1:]:
        if "=" not in part:
            continue
        key, raw_value = part.strip().split("=", maxsplit=1)
        result[key] = raw_value.strip('"')
    return result


def _decode_part_headers(decoded_headers: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for header_line in decoded_headers.split("\r\n"):
        if ":" not in header_line:
            continue
        key, value = header_line.split(":", maxsplit=1)
        headers[key.lower()] = value.strip()
    return headers


def _consume_multipart_part(
    part: bytes,
    fields: dict[str, str],
    images: list[SubmittedImage],
) -> None:
    if not part or part == b"--":
        return
    if part.endswith(b"--"):
        # Trailing junk after the closing boundary.
        return
    if b"\r\n\r\n" not in part:
        logger.warning("Skipping malformed multipart part of length %d", len(part))
        return
    raw_headers, content = part.split(b"\r\n\r\n", maxsplit=1)
    try:
        decoded_headers = raw_headers.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _validation_error("Multipart part headers are not valid UTF-8.") from exc
    headers = _decode_part_headers(decoded_headers)
    disposition = _parse_content_disposition(headers.get("content-disposition", ""))
    name = disposition.get("name")
    if name is None:
        return
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
        return
    try:
        fields[name] = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _validation_error(f"Multipart field {name!r} is not valid UTF-8.") from exc


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
    # Strip exactly one CRLF on each side instead of bytes.strip(),
    # which would silently chew binary file content ending in 0x09/0x0A/0x0B/0x0C/0x0D/0x20.
    for raw_part in body.split(boundary):
        part = raw_part.removeprefix(b"\r\n").removesuffix(b"\r\n")
        _consume_multipart_part(part, fields, images)
    return fields, images


def _validate_images(images: list[SubmittedImage]) -> None:
    if len(images) > _MAX_IMAGE_COUNT:
        raise _validation_error(f"At most {_MAX_IMAGE_COUNT} images may be uploaded.")
    for image in images:
        if image.content_type not in _ALLOWED_IMAGE_TYPES:
            raise _validation_error(
                f"Image {image.filename!r} must be JPEG or PNG."
            )
        if not _content_matches_declared_type(image.content, image.content_type):
            raise _validation_error(
                f"Image {image.filename!r} content does not match its declared type."
            )
        if len(image.content) > _MAX_IMAGE_BYTES:
            raise _validation_error(
                f"Image {image.filename!r} must be {_MAX_IMAGE_MEGABYTES} MB or smaller."
            )


def _content_matches_declared_type(content: bytes, content_type: str) -> bool:
    if content_type == "image/png":
        return content.startswith(_PNG_SIGNATURE)
    if content_type == "image/jpeg":
        return content.startswith(_JPEG_START) and content.endswith(_JPEG_END)
    return False


def _persist_images(
    repair_request: RepairRequest,
    images: list[SubmittedImage],
    storage: ImageStorageDep,
    saved_keys: list[str],
) -> None:
    """Persist images via the storage backend and attach DB rows.

    The caller MUST call ``storage.cleanup(saved_keys)`` if any later step
    (DB flush, commit) fails, otherwise stored objects are orphaned.
    """
    for image in images:
        image_id = str(uuid.uuid4())
        suffix = _ALLOWED_IMAGE_TYPES[image.content_type]
        storage_key = storage.save(
            repair_request_id=repair_request.id,
            image_id=image_id,
            suffix=suffix,
            content=image.content,
        )
        saved_keys.append(storage_key)
        repair_request.images.append(
            RepairImage(
                id=image_id,
                repair_request_id=repair_request.id,
                image_url=storage_key,
            )
        )


async def _repair_payload_from_request(
    request: Request,
) -> tuple[RepairRequestCreate, list[SubmittedImage]]:
    content_type = request.headers.get("content-type", "")

    # DoS guard: cap declared body size before buffering it into memory.
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            content_length = int(declared_length)
        except ValueError as exc:
            raise _validation_error("Invalid Content-Length header.") from exc
        if content_length > _MAX_REQUEST_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Request body exceeds the allowed size.",
            )

    if content_type.startswith("application/json"):
        raw_payload = await request.json()
        return RepairRequestCreate.model_validate(raw_payload), []

    body = await request.body()

    if content_type.startswith("multipart/form-data"):
        fields, images = _parse_multipart_fields(content_type, body)
        _validate_images(images)
        return RepairRequestCreate.model_validate(fields), images

    if content_type.startswith("application/x-www-form-urlencoded"):
        try:
            decoded_body = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _validation_error("Form body is not valid UTF-8.") from exc
        parsed = parse_qs(decoded_body, keep_blank_values=True)
        fields = {key: values[-1] if values else "" for key, values in parsed.items()}
        return RepairRequestCreate.model_validate(fields), []

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=f"Unsupported content-type: {content_type or '<missing>'}",
    )


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
            raise _validation_error(
                f"Unsupported sort field {sort_field!r}. "
                f"Allowed: {sorted(_SORT_COLUMNS)}."
            )
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


@router.get("/{repair_request_id}", summary="Get repair request")
def get_repair_request(
    repair_request_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> DataResponse[RepairRequestRead]:
    try:
        repair_request = _get_repair_request(db, repair_request_id)
        if (
            current_user.role is UserRole.HOLDER
            and repair_request.requester_id != current_user.id
        ):
            raise _forbidden("You do not have access to this repair request.")
        return DataResponse(data=RepairRequestRead.model_validate(repair_request))
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error(
            "Failed to get repair request: %s",
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve repair request. Please try again later.",
        ) from exc


@router.post("/{repair_request_id}/approve", summary="Approve repair request")
def approve_repair_request(
    repair_request_id: str,
    payload: RepairRequestApprove,
    db: DbSession,
    manager: ManagerUser,
) -> DataResponse[RepairRequestRead]:
    try:
        repair_request = _get_repair_request(db, repair_request_id)
        _ensure_request_version(repair_request, payload.version)
        _ensure_request_status(
            repair_request,
            RepairRequestStatus.PENDING_REVIEW,
            "Only pending-review repair requests can be approved.",
        )
        asset = _ensure_asset_status(
            repair_request,
            AssetStatus.PENDING_REPAIR,
            "Associated asset must be pending repair before approval.",
        )

        repair_request.status = RepairRequestStatus.UNDER_REPAIR
        repair_request.reviewer = manager
        asset.status = AssetStatus.UNDER_REPAIR
        return _commit_repair_change(db, repair_request, "Repair request approval")
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Unexpected error in approve_repair_request")
        raise


@router.post("/{repair_request_id}/reject", summary="Reject repair request")
def reject_repair_request(
    repair_request_id: str,
    payload: RepairRequestReject,
    db: DbSession,
    manager: ManagerUser,
) -> DataResponse[RepairRequestRead]:
    try:
        repair_request = _get_repair_request(db, repair_request_id)
        _ensure_request_version(repair_request, payload.version)
        _ensure_request_status(
            repair_request,
            RepairRequestStatus.PENDING_REVIEW,
            "Only pending-review repair requests can be rejected.",
        )
        asset = _ensure_asset_status(
            repair_request,
            AssetStatus.PENDING_REPAIR,
            "Associated asset must be pending repair before rejection.",
        )

        repair_request.status = RepairRequestStatus.REJECTED
        repair_request.rejection_reason = payload.rejection_reason
        repair_request.reviewer = manager
        asset.status = AssetStatus.IN_USE
        return _commit_repair_change(db, repair_request, "Repair request rejection")
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Unexpected error in reject_repair_request")
        raise


@router.patch("/{repair_request_id}/repair-details", summary="Fill repair details")
def update_repair_details(
    repair_request_id: str,
    payload: RepairRequestDetailsUpdate,
    db: DbSession,
    _manager: ManagerUser,
) -> DataResponse[RepairRequestRead]:
    try:
        repair_request = _get_repair_request(db, repair_request_id)
        _ensure_request_version(repair_request, payload.version)
        _ensure_request_status(
            repair_request,
            RepairRequestStatus.UNDER_REPAIR,
            "Repair details can only be updated while the request is under repair.",
        )
        # Defense-in-depth: every other workflow endpoint validates asset
        # status. If state ever desyncs (e.g., asset disposed out-of-band),
        # silently writing repair metadata to it would be wrong.
        _ensure_asset_status(
            repair_request,
            AssetStatus.UNDER_REPAIR,
            "Associated asset must be under repair to update details.",
        )

        update_data = payload.model_dump(exclude={"version"}, exclude_unset=True)
        unknown_fields = set(update_data) - _REPAIR_DETAILS_UPDATABLE_FIELDS
        if unknown_fields:
            logger.error(
                "update_repair_details schema/model drift — unexpected fields: %s",
                sorted(unknown_fields),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal configuration error.",
            )
        for field_name, value in update_data.items():
            setattr(repair_request, field_name, value)
        return _commit_repair_change(db, repair_request, "Repair details update")
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Unexpected error in update_repair_details")
        raise


@router.post("/{repair_request_id}/complete", summary="Complete repair request")
def complete_repair_request(
    repair_request_id: str,
    payload: RepairRequestComplete,
    db: DbSession,
    _manager: ManagerUser,
) -> DataResponse[RepairRequestRead]:
    try:
        repair_request = _get_repair_request(db, repair_request_id)
        _ensure_request_version(repair_request, payload.version)
        _ensure_request_status(
            repair_request,
            RepairRequestStatus.UNDER_REPAIR,
            "Only under-repair requests can be completed.",
        )
        asset = _ensure_asset_status(
            repair_request,
            AssetStatus.UNDER_REPAIR,
            "Associated asset must be under repair before completion.",
        )

        repair_request.repair_date = payload.repair_date
        repair_request.fault_content = payload.fault_content
        repair_request.repair_plan = payload.repair_plan
        repair_request.repair_cost = payload.repair_cost
        repair_request.repair_vendor = payload.repair_vendor
        repair_request.completed_at = datetime.now(UTC)
        repair_request.status = RepairRequestStatus.COMPLETED
        asset.status = AssetStatus.IN_USE
        return _commit_repair_change(db, repair_request, "Repair request completion")
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Unexpected error in complete_repair_request")
        raise


@router.post("", status_code=status.HTTP_201_CREATED, summary="Submit repair request")
async def submit_repair_request(
    request: Request,
    db: DbSession,
    response: Response,
    current_user: HolderUser,
    storage: ImageStorageDep,
) -> DataResponse[RepairRequestRead]:
    saved_keys: list[str] = []
    committed = False
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
        _persist_images(repair_request, images, storage, saved_keys)
        db.flush()
        response.headers["Location"] = f"/api/v1/repair-requests/{repair_request.id}"
        result = DataResponse(data=RepairRequestRead.model_validate(repair_request))
        db.commit()
        committed = True
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
    except OSError as exc:
        db.rollback()
        logger.error("Failed to persist repair-request image: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to store repair images. Please try again later.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to submit repair request: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to submit repair request. Please try again later.",
        ) from exc
    finally:
        if not committed:
            storage.cleanup(saved_keys)
