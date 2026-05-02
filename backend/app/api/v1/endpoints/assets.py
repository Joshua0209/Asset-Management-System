import logging
import math
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError

from app.api.deps import CurrentUser, HolderUser, ManagerUser
from app.db.session import get_db
from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole
from app.schemas.asset import (
    AssetAssignRequest,
    AssetCreate,
    AssetDisposeRequest,
    AssetRead,
    AssetUnassignRequest,
    AssetUpdate,
)
from app.schemas.common import DataResponse, PaginatedListResponse, PaginationMeta

logger = logging.getLogger(__name__)
router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]

_SORT_COLUMNS = {
    "created_at": Asset.created_at,
    "name": Asset.name,
    "asset_code": Asset.asset_code,
    "purchase_date": Asset.purchase_date,
    "status": Asset.status,
}
_ASSET_CODE_CREATE_ATTEMPTS = 3
_ACTIVE_REPAIR_STATUSES = {
    RepairRequestStatus.PENDING_REVIEW,
    RepairRequestStatus.UNDER_REPAIR,
}
_STALE_VERSION_MESSAGE = (
    "Resource was modified by another user. Please refresh and try again."
)


def _safe_log(value: object) -> str:
    # Escape CR/LF so user-controlled path params cannot forge log entries (CWE-117).
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


def _next_asset_code(db: Session, today: date | None = None) -> str:
    year = (today or date.today()).year
    prefix = f"AST-{year}-"
    latest_code = db.scalar(
        select(Asset.asset_code)
        .where(Asset.asset_code.like(f"{prefix}%"))
        .order_by(Asset.asset_code.desc())
        .limit(1)
    )
    if latest_code is None:
        return f"{prefix}{1:05d}"
    try:
        next_sequence = int(latest_code.rsplit("-", maxsplit=1)[1]) + 1
    except (IndexError, ValueError) as exc:
        # Don't silently fall back to 00001 — that would re-collide on every retry.
        logger.error(
            "Existing asset_code does not match expected format: prefix=%s latest=%r",
            prefix,
            latest_code,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Asset code sequence is corrupted. Contact an administrator.",
        ) from exc
    return f"{prefix}{next_sequence:05d}"


def _is_asset_code_uniqueness_violation(exc: IntegrityError) -> bool:
    """Best-effort check that an IntegrityError is the asset_code unique constraint."""
    message = str(getattr(exc, "orig", None) or exc).lower()
    return "asset_code" in message


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _validation_error(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message)


def _asset_from_payload(payload: AssetCreate, asset_code: str) -> Asset:
    return Asset(
        asset_code=asset_code,
        name=payload.name,
        model=payload.model,
        specs=payload.specs,
        category=payload.category,
        supplier=payload.supplier,
        purchase_date=payload.purchase_date,
        purchase_amount=payload.purchase_amount,
        location=payload.location or "",
        department=payload.department or "",
        activation_date=payload.activation_date,
        warranty_expiry=payload.warranty_expiry,
        status=AssetStatus.IN_STOCK,
        responsible_person_id=None,
    )


def _base_filters() -> list[ColumnElement[bool]]:
    return [Asset.deleted_at.is_(None)]


def _build_asset_filters(
    *,
    q: str | None,
    status_filter: AssetStatus | None,
    category: str | None,
    department: str | None,
    location: str | None,
    responsible_person_id: str | None,
) -> list[ColumnElement[bool]]:
    filters = _base_filters()
    if q:
        pattern = f"%{q}%"
        filters.append(
            or_(
                Asset.asset_code.ilike(pattern),
                Asset.name.ilike(pattern),
                Asset.model.ilike(pattern),
            )
        )
    if status_filter is not None:
        filters.append(Asset.status == status_filter)
    if category:
        filters.append(Asset.category == category)
    if department:
        filters.append(Asset.department == department)
    if location:
        filters.append(Asset.location == location)
    if responsible_person_id:
        filters.append(Asset.responsible_person_id == responsible_person_id)
    return filters


def _asset_order(sort: str) -> ColumnElement[object]:
    sort_desc = sort.startswith("-")
    sort_field = sort[1:] if sort_desc else sort
    sort_column = _SORT_COLUMNS.get(sort_field)
    if sort_column is None:
        raise _validation_error(
            f"Unsupported sort field {sort_field!r}. "
            f"Allowed: {sorted(_SORT_COLUMNS)}."
        )
    return sort_column.desc() if sort_desc else sort_column.asc()


def _list_asset_response(
    *,
    db: Session,
    filters: list[ColumnElement[bool]],
    page: int,
    per_page: int,
    sort: str,
) -> PaginatedListResponse[AssetRead]:
    total = db.scalar(select(func.count()).select_from(Asset).where(*filters)) or 0
    assets = db.scalars(
        select(Asset)
        .options(joinedload(Asset.responsible_person.and_(User.deleted_at.is_(None))))
        .where(*filters)
        .order_by(_asset_order(sort))
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    return PaginatedListResponse(
        data=[AssetRead.model_validate(asset) for asset in assets],
        meta=PaginationMeta(
            total=total,
            page=page,
            per_page=per_page,
            total_pages=math.ceil(total / per_page) if total else 0,
        ),
    )


@router.get("", summary="List assets")
def list_assets(
    db: DbSession,
    _manager: ManagerUser,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    q: str | None = None,
    status_filter: Annotated[AssetStatus | None, Query(alias="status")] = None,
    category: str | None = None,
    department: str | None = None,
    location: str | None = None,
    responsible_person_id: str | None = None,
    sort: str = "-created_at",
) -> PaginatedListResponse[AssetRead]:
    try:
        filters = _build_asset_filters(
            q=q,
            status_filter=status_filter,
            category=category,
            department=department,
            location=location,
            responsible_person_id=responsible_person_id,
        )
        return _list_asset_response(
            db=db,
            filters=filters,
            page=page,
            per_page=per_page,
            sort=sort,
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.error("Failed to list assets: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve assets. Please try again later.",
        ) from exc


@router.post("", status_code=status.HTTP_201_CREATED, summary="Register an asset")
def register_asset(
    payload: AssetCreate,
    db: DbSession,
    response: Response,
    _manager: ManagerUser,
) -> DataResponse[AssetRead]:
    last_integrity_error: IntegrityError | None = None
    for attempt in range(1, _ASSET_CODE_CREATE_ATTEMPTS + 1):
        try:
            asset = _asset_from_payload(payload, _next_asset_code(db))
            db.add(asset)
            db.flush()
            response.headers["Location"] = f"/api/v1/assets/{asset.id}"
            result = DataResponse(data=AssetRead.model_validate(asset))
            db.commit()
            return result
        except IntegrityError as exc:
            db.rollback()
            if not _is_asset_code_uniqueness_violation(exc):
                # A non-asset_code constraint violation will keep failing on retry;
                # surface it as a validation error instead of a misleading 409.
                logger.error(
                    "Non-uniqueness IntegrityError during asset registration: %s",
                    exc,
                    exc_info=True,
                )
                raise _validation_error(
                    "Asset registration violates database constraints."
                ) from exc
            last_integrity_error = exc
            logger.warning(
                "asset_code race on attempt %s/%s: %s",
                attempt,
                _ASSET_CODE_CREATE_ATTEMPTS,
                exc,
            )
        except SQLAlchemyError as exc:
            db.rollback()
            logger.error("Failed to register asset: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to register asset. Please try again later.",
            ) from exc
    logger.error(
        "Asset registration exhausted %s retries; possible asset_code corruption or hot collision",
        _ASSET_CODE_CREATE_ATTEMPTS,
    )
    raise _conflict(
        "Asset code already exists. Please retry asset registration."
    ) from last_integrity_error


@router.get("/mine", summary="List assets assigned to current holder")
def list_my_assets(
    db: DbSession,
    current_user: HolderUser,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    q: str | None = None,
    status_filter: Annotated[AssetStatus | None, Query(alias="status")] = None,
    category: str | None = None,
    department: str | None = None,
    location: str | None = None,
    sort: str = "-created_at",
) -> PaginatedListResponse[AssetRead]:
    try:
        filters = _build_asset_filters(
            q=q,
            status_filter=status_filter,
            category=category,
            department=department,
            location=location,
            responsible_person_id=current_user.id,
        )
        return _list_asset_response(
            db=db,
            filters=filters,
            page=page,
            per_page=per_page,
            sort=sort,
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.error("Failed to list assigned assets: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve assets. Please try again later.",
        ) from exc


@router.get("/{asset_id}", summary="Get an asset")
def get_asset(asset_id: str, db: DbSession, current_user: CurrentUser) -> DataResponse[AssetRead]:
    try:
        asset = db.scalar(
            select(Asset)
            .options(joinedload(Asset.responsible_person.and_(User.deleted_at.is_(None))))
            .where(Asset.id == asset_id, Asset.deleted_at.is_(None))
        )
        if asset is None:
            raise _not_found()
        if (
            current_user.role is not UserRole.MANAGER
            and asset.responsible_person_id != current_user.id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this asset.",
            )
        return DataResponse(data=AssetRead.model_validate(asset))
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.error("Failed to get asset %s: %s", asset_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve asset. Please try again later.",
        ) from exc


@router.patch("/{asset_id}", summary="Update asset info")
def update_asset(
    asset_id: str,
    payload: AssetUpdate,
    db: DbSession,
    _manager: ManagerUser,
) -> DataResponse[AssetRead]:
    try:
        asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None)))
        if asset is None:
            raise _not_found()

        update_data = payload.model_dump(exclude={"version"}, exclude_unset=True)
        # Cross-field validation runs before the version check so a stale-version
        # client with bad data sees the validation error on the first round-trip.
        purchase_date = update_data.get("purchase_date", asset.purchase_date)
        warranty_expiry = update_data.get("warranty_expiry", asset.warranty_expiry)
        if warranty_expiry is not None and warranty_expiry <= purchase_date:
            raise _validation_error("warranty_expiry must be after purchase_date.")

        if asset.version != payload.version:
            raise _conflict(_STALE_VERSION_MESSAGE)

        for field_name, value in update_data.items():
            if field_name in {"location", "department"} and value is None:
                value = ""
            setattr(asset, field_name, value)

        db.commit()
        db.refresh(asset)
        return DataResponse(data=AssetRead.model_validate(asset))
    except HTTPException:
        raise
    except StaleDataError as exc:
        db.rollback()
        logger.warning("Asset update conflict for %s: %s", asset_id, exc)
        raise _conflict(
            _STALE_VERSION_MESSAGE
        ) from exc
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Invalid asset update for %s: %s", asset_id, exc)
        raise _validation_error("Asset update violates database constraints.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to update asset %s: %s", asset_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to update asset. Please try again later.",
        ) from exc


def _load_asset_for_transition(db: Session, asset_id: str) -> Asset:
    asset = db.scalar(
        select(Asset)
        .options(joinedload(Asset.responsible_person.and_(User.deleted_at.is_(None))))
        .where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    if asset is None:
        raise _not_found()
    return asset


def _has_active_repair_request(db: Session, asset_id: str) -> bool:
    count = db.scalar(
        select(func.count())
        .select_from(RepairRequest)
        .where(
            RepairRequest.asset_id == asset_id,
            RepairRequest.deleted_at.is_(None),
            RepairRequest.status.in_(_ACTIVE_REPAIR_STATUSES),
        )
    )
    return bool(count)


def _transition_503(asset_id: str, exc: SQLAlchemyError, action: str) -> HTTPException:
    logger.error("Failed to %s asset %s: %s", action, _safe_log(asset_id), exc, exc_info=True)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Unable to {action} asset. Please try again later.",
    )


@router.post("/{asset_id}/assign", summary="Assign asset to a holder (FSM T2)")
def assign_asset(
    asset_id: str,
    payload: AssetAssignRequest,
    db: DbSession,
    _manager: ManagerUser,
) -> DataResponse[AssetRead]:
    try:
        asset = _load_asset_for_transition(db, asset_id)

        target = db.scalar(
            select(User).where(
                User.id == payload.responsible_person_id,
                User.deleted_at.is_(None),
                User.role == UserRole.HOLDER,
            )
        )
        if target is None:
            raise _validation_error(
                "responsible_person_id must reference an active holder."
            )

        if asset.status is not AssetStatus.IN_STOCK:
            raise _conflict("Asset must be in_stock to assign.")
        if asset.responsible_person_id is not None:
            raise _conflict("Asset already has a responsible person.")
        if asset.version != payload.version:
            raise _conflict(
                _STALE_VERSION_MESSAGE
            )

        asset.status = AssetStatus.IN_USE
        asset.responsible_person_id = target.id
        asset.responsible_person = target
        db.commit()
        db.refresh(asset)
        return DataResponse(data=AssetRead.model_validate(asset))
    except HTTPException:
        raise
    except StaleDataError as exc:
        db.rollback()
        logger.warning("Asset assign conflict for %s: %s", _safe_log(asset_id), exc)
        raise _conflict(
            _STALE_VERSION_MESSAGE
        ) from exc
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Invalid asset assign for %s: %s", _safe_log(asset_id), exc)
        raise _validation_error("Asset assignment violates database constraints.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise _transition_503(asset_id, exc, "assign") from exc


@router.post("/{asset_id}/unassign", summary="Unassign / reclaim asset (FSM T5)")
def unassign_asset(
    asset_id: str,
    payload: AssetUnassignRequest,
    db: DbSession,
    manager: ManagerUser,
) -> DataResponse[AssetRead]:
    try:
        asset = _load_asset_for_transition(db, asset_id)

        if asset.status is not AssetStatus.IN_USE:
            raise _conflict("Asset must be in_use to unassign.")
        # Belt-and-suspenders: per FSM T5, an active repair request blocks unassign even
        # if the asset's status somehow remained in_use through a prior bug.
        if _has_active_repair_request(db, asset.id):
            raise _conflict("Cannot unassign asset with an active repair request.")
        if asset.version != payload.version:
            raise _conflict(
                _STALE_VERSION_MESSAGE
            )

        # Reason is validated by the schema and recorded in the application log; persistent
        # audit trail lands in Week 4 with the asset_action_histories table.
        logger.info(
            "Asset %s unassigned by %s. reason=%r",
            asset.asset_code,
            manager.id,
            payload.reason,
        )

        asset.status = AssetStatus.IN_STOCK
        asset.responsible_person_id = None
        asset.responsible_person = None
        db.commit()
        db.refresh(asset)
        return DataResponse(data=AssetRead.model_validate(asset))
    except HTTPException:
        raise
    except StaleDataError as exc:
        db.rollback()
        logger.warning("Asset unassign conflict for %s: %s", _safe_log(asset_id), exc)
        raise _conflict(
            _STALE_VERSION_MESSAGE
        ) from exc
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Invalid asset unassign for %s: %s", _safe_log(asset_id), exc)
        raise _validation_error("Asset unassign violates database constraints.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise _transition_503(asset_id, exc, "unassign") from exc


@router.post("/{asset_id}/dispose", summary="Scrap asset (FSM T3)")
def dispose_asset(
    asset_id: str,
    payload: AssetDisposeRequest,
    db: DbSession,
    _manager: ManagerUser,
) -> DataResponse[AssetRead]:
    try:
        asset = _load_asset_for_transition(db, asset_id)

        if asset.status is not AssetStatus.IN_STOCK:
            raise _conflict("Asset must be in_stock to dispose.")
        if asset.responsible_person_id is not None:
            raise _conflict("Cannot dispose asset that is still assigned to a holder.")
        if asset.version != payload.version:
            raise _conflict(
                _STALE_VERSION_MESSAGE
            )

        asset.status = AssetStatus.DISPOSED
        asset.disposal_reason = payload.disposal_reason
        db.commit()
        db.refresh(asset)
        return DataResponse(data=AssetRead.model_validate(asset))
    except HTTPException:
        raise
    except StaleDataError as exc:
        db.rollback()
        logger.warning("Asset dispose conflict for %s: %s", _safe_log(asset_id), exc)
        raise _conflict(
            _STALE_VERSION_MESSAGE
        ) from exc
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Invalid asset dispose for %s: %s", _safe_log(asset_id), exc)
        raise _validation_error("Asset disposal violates database constraints.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise _transition_503(asset_id, exc, "dispose") from exc
