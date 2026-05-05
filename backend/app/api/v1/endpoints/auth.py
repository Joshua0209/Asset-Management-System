from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, ManagerUser
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.auth import (
    AdminCreateUserRequest,
    LoginRequest,
    LoginResponse,
    LoginUser,
    RegisterRequest,
)
from app.schemas.common import DataResponse, error_responses
from app.schemas.user import UserRead

logger = logging.getLogger(__name__)
router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]

_EMAIL_ALREADY_REGISTERED = "Email is already registered"


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register new user (public, holder-only)",
    responses=error_responses(
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)
def register(payload: RegisterRequest, db: DbSession) -> DataResponse[UserRead]:
    # Decision A2: role is always holder on public register.
    # Email is globally unique at the DB layer, so the duplicate check is
    # not filtered by deleted_at — a soft-deleted row still occupies the email.
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_EMAIL_ALREADY_REGISTERED,
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
            detail=_EMAIL_ALREADY_REGISTERED,
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


@router.post(
    "/login",
    summary="Authenticate and receive an access token",
    responses=error_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ),
)
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


@router.get(
    "/me",
    summary="Get the authenticated user's profile",
    responses=error_responses(status.HTTP_401_UNAUTHORIZED),
)
def me(current_user: CurrentUser) -> DataResponse[UserRead]:
    return DataResponse(data=UserRead.model_validate(current_user))


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    summary="Create a user of any role (manager-only)",
    responses=error_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)
def admin_create_user(
    payload: AdminCreateUserRequest,
    db: DbSession,
    _actor: ManagerUser,
) -> DataResponse[UserRead]:
    """Decision A2 escape hatch: managers create both holders and managers here.

    Public /auth/register is holder-only; this endpoint is how the team adds
    additional managers once the bootstrap manager has logged in.
    """
    # Same global-uniqueness reasoning as /auth/register — see note above.
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_EMAIL_ALREADY_REGISTERED,
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        role=payload.role,
        department=payload.department,
    )
    try:
        db.add(user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_EMAIL_ALREADY_REGISTERED,
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to create user via admin endpoint: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to create user. Please try again later.",
        ) from exc

    db.refresh(user)
    return DataResponse(data=UserRead.model_validate(user))
