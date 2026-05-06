import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, cast
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import ValidationError
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
from app.db.session import get_db
from app.models.asset import Asset, AssetStatus
from app.models.asset_action_history import AssetAction
from app.models.repair_image import RepairImage
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import UserRole
from app.schemas.common import (
    DataResponse,
    PaginatedListResponse,
    PaginationMeta,
    UUIDPath,
    error_responses,
)
from app.schemas.repair_request import (
    RepairRequestApprove,
    RepairRequestComplete,
    RepairRequestCreate,
    RepairRequestDetailsUpdate,
    RepairRequestRead,
    RepairRequestReject,
)
from app.services.audit_log import record_asset_action
from app.services.image_storage import ImageStorageDep, ImageStorageError

logger = logging.getLogger(__name__)
router = APIRouter(
    responses=error_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )
)

DbSession = Annotated[Session, Depends(get_db)]
RepairRequestIdPath = UUIDPath

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

_ERROR_RESPONSES = error_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_409_CONFLICT,
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    status.HTTP_422_UNPROCESSABLE_ENTITY,
    status.HTTP_503_SERVICE_UNAVAILABLE,
)

def _build_repair_submit_openapi_extra() -> dict[str, Any]:
    """Build the multipart schema from `RepairRequestCreate` so it never drifts.

    The `application/json` and `application/x-www-form-urlencoded` bodies share
    the auto-generated schema via $ref. The multipart variant has to be hand
    composed because it adds an `images` file array, but its scalar fields
    must stay in lockstep with the Pydantic model — so we read them out of
    `model_json_schema()` rather than hard-coding them a second time.
    """
    base_schema = RepairRequestCreate.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )
    multipart_properties = dict(base_schema.get("properties", {}))
    multipart_properties["images"] = {
        "type": "array",
        "maxItems": _MAX_IMAGE_COUNT,
        "items": {"type": "string", "format": "binary"},
        "description": (
            "Optional JPEG/PNG repair images; max "
            f"{_MAX_IMAGE_COUNT} files, {_MAX_IMAGE_MEGABYTES} MB each."
        ),
    }
    return {
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/RepairRequestCreate"}
                },
                "application/x-www-form-urlencoded": {
                    "schema": {"$ref": "#/components/schemas/RepairRequestCreate"}
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": list(base_schema.get("required", [])),
                        "properties": multipart_properties,
                    },
                    "encoding": {
                        "images": {
                            # OpenAPI 3.x prefers a comma+space separator.
                            "contentType": ", ".join(sorted(_ALLOWED_IMAGE_TYPES)),
                        }
                    },
                },
            },
        }
    }


_REPAIR_SUBMIT_OPENAPI_EXTRA: dict[str, Any] = _build_repair_submit_openapi_extra()


@dataclass(frozen=True, kw_only=True)
class SubmittedImage:
    filename: str
    content_type: str
    content: bytes


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def _conflict(message: str, *, code: str = "conflict") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message},
    )


def _validation_error(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message)


def _repair_create_from_mapping(raw_payload: object) -> RepairRequestCreate:
    try:
        return RepairRequestCreate.model_validate(raw_payload)
    except ValidationError as exc:
        details = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ())),
                "message": error.get("msg", ""),
                "code": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "validation_error",
                "message": "Validation failed",
                "details": details,
            },
        ) from exc


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
        raise _conflict(message, code="invalid_transition")
    return cast(Asset, asset)


def _ensure_request_status(
    repair_request: RepairRequest,
    expected_status: RepairRequestStatus,
    message: str,
) -> None:
    if repair_request.status is not expected_status:
        raise _conflict(message, code="invalid_transition")


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
        # Transient — caller may retry.
        db.rollback()
        logger.error("%s transient DB error: %s", log_context, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to update repair request. Please try again later.",
        ) from exc
    except IntegrityError as exc:
        # State conflict — not retryable.
        db.rollback()
        # exc_info=True so the traceback identifies which setattr corrupted
        # state (str(IntegrityError) truncates at [parameters: ...] and
        # discards the call-site frame).
        logger.warning("%s integrity error: %s", log_context, exc, exc_info=True)
        raise _conflict(
            "Repair request could not be updated due to a conflicting state."
        ) from exc
    except DataError as exc:
        # Caller's input → validation_error (422).
        db.rollback()
        logger.warning("%s data error: %s", log_context, exc, exc_info=True)
        raise _validation_error(
            "Repair request payload contains invalid values."
        ) from exc
    except SQLAlchemyError as exc:
        # Programmer bug — generic 500.
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
    # Empty preamble or post-closing-boundary segment (`--` followed by an
    # optional RFC 7578 epilogue). Don't use `endswith(b"--")` here:
    # legitimate content (e.g. a fault_description ending with "--") would be
    # silently dropped.
    if not part or part.startswith(b"--"):
        return
    if b"\r\n\r\n" not in part:
        raise _validation_error("Malformed multipart part.")
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


def _enforce_request_size_limit(declared_length: str | None) -> None:
    """DoS guard: reject oversized bodies before buffering them into memory."""
    if declared_length is None:
        return
    try:
        content_length = int(declared_length)
    except ValueError as exc:
        raise _validation_error("Invalid Content-Length header.") from exc
    if content_length > _MAX_REQUEST_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Request body exceeds the allowed size.",
        )


def _parse_form_urlencoded(body: bytes) -> dict[str, str]:
    try:
        decoded_body = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _validation_error("Form body is not valid UTF-8.") from exc
    parsed = parse_qs(decoded_body, keep_blank_values=True)
    duplicates = [key for key, values in parsed.items() if len(values) > 1]
    if duplicates:
        # Every documented field is scalar; "last wins" would silently
        # discard data. Reject up front so the client sees the bug.
        raise _validation_error(
            f"Form fields appear multiple times: {sorted(duplicates)}."
        )
    return {key: values[0] if values else "" for key, values in parsed.items()}


def _unsupported_media_type(content_type: str) -> HTTPException:
    # Cap the echoed content-type so a malicious client can't bloat the
    # response or smuggle CR/LF into log destinations that render as text.
    safe_content_type = (
        (content_type[:120].replace("\r", "").replace("\n", ""))
        if content_type
        else "<missing>"
    )
    return HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=f"Unsupported content-type: {safe_content_type}",
    )


async def _repair_payload_from_request(
    request: Request,
) -> tuple[RepairRequestCreate, list[SubmittedImage]]:
    content_type = request.headers.get("content-type", "")
    _enforce_request_size_limit(request.headers.get("content-length"))

    if content_type.startswith("application/json"):
        try:
            raw_payload = await request.json()
        except json.JSONDecodeError as exc:
            raise _validation_error("Malformed JSON body.") from exc
        return _repair_create_from_mapping(raw_payload), []

    body = await request.body()

    if content_type.startswith("multipart/form-data"):
        fields, images = _parse_multipart_fields(content_type, body)
        _validate_images(images)
        return _repair_create_from_mapping(fields), images

    if content_type.startswith("application/x-www-form-urlencoded"):
        fields = _parse_form_urlencoded(body)
        return _repair_create_from_mapping(fields), []

    raise _unsupported_media_type(content_type)


@router.get("", summary="List repair requests")
def list_repair_requests(
    db: DbSession,
    current_user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[RepairRequestStatus | None, Query(alias="status")] = None,
    asset_id: UUID | None = None,
    requester_id: UUID | None = None,
    sort: str = "-created_at",
) -> PaginatedListResponse[RepairRequestRead]:
    try:
        filters = _base_filters()
        if status_filter is not None:
            filters.append(RepairRequest.status == status_filter)
        if asset_id:
            filters.append(RepairRequest.asset_id == str(asset_id))
        requester_id_str = str(requester_id) if requester_id else None
        if current_user.role is UserRole.HOLDER:
            if requester_id_str is not None and requester_id_str != current_user.id:
                raise _forbidden("Holder users can only list their own repair requests.")
            filters.append(RepairRequest.requester_id == current_user.id)
        elif requester_id_str:
            filters.append(RepairRequest.requester_id == requester_id_str)

        sort_desc = sort.startswith("-")
        sort_field = sort[1:] if sort_desc else sort
        sort_column = _SORT_COLUMNS.get(sort_field)
        if sort_column is None:
            allowed = ", ".join(sorted(_SORT_COLUMNS))
            raise _validation_error(
                f"Unsupported sort field {sort_field!r}. Allowed: {allowed}."
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
            meta=PaginationMeta(total=total, page=page, per_page=per_page),
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.error("Failed to list repair requests: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve repair requests. Please try again later.",
        ) from exc


@router.get(
    "/{repair_request_id}",
    summary="Get repair request",
    responses=error_responses(status.HTTP_404_NOT_FOUND),
)
def get_repair_request(
    repair_request_id: RepairRequestIdPath,
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
        # Read-only handler — no rollback needed; consistent with list_assets,
        # list_repair_requests, get_asset, list_asset_history.
        logger.error(
            "Failed to get repair request: %s",
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve repair request. Please try again later.",
        ) from exc


@router.post(
    "/{repair_request_id}/approve",
    summary="Approve repair request",
    responses=error_responses(status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT),
)
def approve_repair_request(
    repair_request_id: RepairRequestIdPath,
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

        from_status = asset.status
        repair_request.status = RepairRequestStatus.UNDER_REPAIR
        repair_request.reviewer = manager
        asset.status = AssetStatus.UNDER_REPAIR
        record_asset_action(
            db,
            asset=asset,
            actor=manager,
            action=AssetAction.APPROVE_REPAIR,
            from_status=from_status,
            to_status=AssetStatus.UNDER_REPAIR,
            metadata={"repair_request_id": repair_request.id},
        )
        return _commit_repair_change(db, repair_request, "Repair request approval")
    except HTTPException:
        # _commit_repair_change owns rollback for the commit path; precondition
        # raises (_ensure_*) happen before any pending writes.
        raise
    except Exception:
        # Catch-all so the audit row never lands without the FSM commit. The
        # raised exception is rewrapped into the project envelope by the
        # global handler in app/main.py.
        db.rollback()
        logger.exception("Unexpected error in approve_repair_request")
        raise


@router.post(
    "/{repair_request_id}/reject",
    summary="Reject repair request",
    responses=error_responses(status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT),
)
def reject_repair_request(
    repair_request_id: RepairRequestIdPath,
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

        from_status = asset.status
        repair_request.status = RepairRequestStatus.REJECTED
        repair_request.rejection_reason = payload.rejection_reason
        repair_request.reviewer = manager
        asset.status = AssetStatus.IN_USE
        record_asset_action(
            db,
            asset=asset,
            actor=manager,
            action=AssetAction.REJECT_REPAIR,
            from_status=from_status,
            to_status=AssetStatus.IN_USE,
            metadata={
                "repair_request_id": repair_request.id,
                "rejection_reason": payload.rejection_reason,
            },
        )
        return _commit_repair_change(db, repair_request, "Repair request rejection")
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("Unexpected error in reject_repair_request")
        raise


@router.patch(
    "/{repair_request_id}/repair-details",
    summary="Fill repair details",
    responses=error_responses(
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
def update_repair_details(
    repair_request_id: RepairRequestIdPath,
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
        raise
    except Exception:
        db.rollback()
        logger.exception("Unexpected error in update_repair_details")
        raise


@router.post(
    "/{repair_request_id}/complete",
    summary="Complete repair request",
    responses=error_responses(status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT),
)
def complete_repair_request(
    repair_request_id: RepairRequestIdPath,
    payload: RepairRequestComplete,
    db: DbSession,
    manager: ManagerUser,
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

        from_status = asset.status
        repair_request.repair_date = payload.repair_date
        repair_request.fault_content = payload.fault_content
        repair_request.repair_plan = payload.repair_plan
        repair_request.repair_cost = payload.repair_cost
        repair_request.repair_vendor = payload.repair_vendor
        repair_request.completed_at = datetime.now(UTC)
        repair_request.status = RepairRequestStatus.COMPLETED
        asset.status = AssetStatus.IN_USE
        record_asset_action(
            db,
            asset=asset,
            actor=manager,
            action=AssetAction.COMPLETE_REPAIR,
            from_status=from_status,
            to_status=AssetStatus.IN_USE,
            metadata={
                "repair_request_id": repair_request.id,
                # Decimal → str so the JSON column encodes deterministically
                # (and survives MySQL's JSON dialect without precision drift).
                "repair_cost": str(payload.repair_cost),
                "repair_vendor": payload.repair_vendor,
            },
        )
        return _commit_repair_change(db, repair_request, "Repair request completion")
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("Unexpected error in complete_repair_request")
        raise


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Submit repair request",
    responses=_ERROR_RESPONSES,
    openapi_extra=_REPAIR_SUBMIT_OPENAPI_EXTRA,
)
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
            raise _conflict(
                "Repair request is only allowed for assets in use.",
                code="invalid_transition",
            )

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
            raise _conflict(
                "Repair request already exists for this asset.",
                code="duplicate_request",
            )

        repair_request = RepairRequest(
            asset_id=asset.id,
            requester_id=current_user.id,
            status=RepairRequestStatus.PENDING_REVIEW,
            fault_description=payload.fault_description,
        )
        repair_request.asset = asset
        repair_request.requester = current_user
        from_status = asset.status
        asset.status = AssetStatus.PENDING_REPAIR
        db.add(repair_request)
        db.flush()
        # Audit row needs repair_request.id, so it sits between the flush
        # that assigns the PK and the flush that lays down image rows.
        record_asset_action(
            db,
            asset=asset,
            actor=current_user,
            action=AssetAction.SUBMIT_REPAIR,
            from_status=from_status,
            to_status=AssetStatus.PENDING_REPAIR,
            metadata={
                "repair_request_id": repair_request.id,
                "fault_description": payload.fault_description,
            },
        )
        _persist_images(repair_request, images, storage, saved_keys)
        db.flush()
        response.headers["Location"] = f"/api/v1/repair-requests/{repair_request.id}"
        result = DataResponse(data=RepairRequestRead.model_validate(repair_request))
        db.commit()
        committed = True
        return result
    except HTTPException:
        # Roll back any pending FSM mutation / audit row / image FK rows so
        # the session never half-commits when a precondition raises.
        db.rollback()
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
    except (ImageStorageError, OSError) as exc:
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
    except Exception:
        # Catch-all so the audit row never lands without the FSM commit (e.g.,
        # if record_asset_action raises a non-DB exception). The exception is
        # rewrapped into the project envelope by the global handler in
        # app/main.py.
        db.rollback()
        logger.exception("Unexpected error in submit_repair_request")
        raise
    finally:
        if not committed and saved_keys:
            try:
                storage.cleanup(saved_keys)
            except Exception:
                # cleanup runs from a `finally` block; never let it mask the
                # exception we're already propagating. Orphaned keys are logged
                # so they can be reconciled out-of-band.
                logger.exception(
                    "Image cleanup failed; orphaned storage keys: %s",
                    saved_keys,
                )
