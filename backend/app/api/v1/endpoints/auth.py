from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.auth import RegisterRequest
from app.schemas.common import DataResponse
from app.schemas.user import UserRead

logger = logging.getLogger(__name__)
router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register new user (public, holder-only)",
)
def register(payload: RegisterRequest, db: DbSession) -> DataResponse[UserRead]:
    # Decision A2: role is always holder on public register.
    existing = db.scalar(
        select(User).where(User.email == payload.email, User.deleted_at.is_(None))
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        role=UserRole.HOLDER,
        department=payload.department,
    )
    try:
        db.add(user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to register user: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to register user. Please try again later.",
        ) from exc

    db.refresh(user)
    return DataResponse(data=UserRead.model_validate(user))
