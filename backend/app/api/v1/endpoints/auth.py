from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, LoginResponse, LoginUser, RegisterRequest
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


_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid email or password",
)


@router.post("/login", summary="Authenticate and receive an access token")
def login(payload: LoginRequest, db: DbSession) -> DataResponse[LoginResponse]:
    user = db.scalar(
        select(User).where(User.email == payload.email, User.deleted_at.is_(None))
    )
    # Verify a bcrypt string even when the user doesn't exist, so response
    # timing does not reveal which emails are registered.
    if user is None:
        verify_password(payload.password, "$2b$12$" + "x" * 53)
        raise _INVALID_CREDENTIALS

    if not verify_password(payload.password, user.password_hash):
        raise _INVALID_CREDENTIALS

    token, expires_at = create_access_token(subject=user.id, role=user.role)
    return DataResponse(
        data=LoginResponse(
            token=token,
            expires_at=expires_at,
            user=LoginUser.model_validate(user),
        )
    )


@router.get("/me", summary="Get the authenticated user's profile")
def me(current_user: CurrentUser) -> DataResponse[UserRead]:
    return DataResponse(data=UserRead.model_validate(current_user))
