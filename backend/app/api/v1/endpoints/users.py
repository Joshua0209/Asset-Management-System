import logging
import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import ManagerUser
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.common import PaginatedListResponse, PaginationMeta
from app.schemas.user import UserRead

logger = logging.getLogger(__name__)
router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", summary="List users")
def list_users(
    db: DbSession,
    _current: ManagerUser,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    role: UserRole | None = None,
    department: str | None = None,
    q: str | None = None,
) -> PaginatedListResponse[UserRead]:
    try:
        filters: list[ColumnElement[bool]] = [User.deleted_at.is_(None)]
        if role is not None:
            filters.append(User.role == role)
        if department is not None:
            filters.append(User.department == department)
        if q:
            pattern = f"%{q}%"
            filters.append(or_(User.name.ilike(pattern), User.email.ilike(pattern)))

        total = db.scalar(select(func.count()).select_from(User).where(*filters)) or 0
        users = db.scalars(
            select(User)
            .where(*filters)
            .order_by(User.name)
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).all()
        return PaginatedListResponse(
            data=[UserRead.model_validate(user) for user in users],
            meta=PaginationMeta(
                total=total,
                page=page,
                per_page=per_page,
                total_pages=math.ceil(total / per_page) if total else 0,
            ),
        )
    except SQLAlchemyError as exc:
        logger.error("Failed to list users: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve users. Please try again later.",
        ) from exc
