from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, ManagerUser
from app.core.config import get_settings
from app.core.rate_limit import limiter
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

_settings = get_settings()

logger = logging.getLogger(__name__)
# Routes here have heterogeneous auth requirements (`/register` is public,
# `/me` is read-only authed, `/users` is manager-only), so the router does
# not declare a shared `responses=` block — each endpoint enumerates its
# real errors individually instead of inheriting a misleading default.
router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]

_EMAIL_ALREADY_REGISTERED = "Email is already registered"
_USER_CREATE_UNAVAILABLE = "Unable to create user. Please try again later."


def _is_email_uniqueness_violation(exc: IntegrityError) -> bool:
    """Best-effort check that an IntegrityError is the users.email unique constraint.

    Without this guard we would mask any unique constraint violation as
    "email already registered", which is misleading if a future schema change
    adds another unique column.
    """
    message = str(getattr(exc, "orig", None) or exc).lower()
    return "email" in message

# Real bcrypt hash used to equalize response time when an unknown email logs
# in. A bcrypt-shaped string like "$2b$12$" + "x"*53 raises ``ValueError`` at
# the C layer in ~0ms, so it would not equalize anything — bcrypt.checkpw
# must do real work for the timing protection to hold.
_DUMMY_PASSWORD_HASH = hash_password("placeholder-password-for-timing-equalization")  # noqa: S106


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register new user (public, holder-only)",
    responses=error_responses(
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)
@limiter.limit(_settings.rate_limit_anonymous)
def register(
    request: Request, payload: RegisterRequest, db: DbSession
) -> DataResponse[UserRead]:
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
        if not _is_email_uniqueness_violation(exc):
            logger.error(
                "Unexpected IntegrityError on user create: %s", exc, exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_USER_CREATE_UNAVAILABLE,
            ) from exc
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
        status.HTTP_429_TOO_MANY_REQUESTS,
    ),
)
@limiter.limit(_settings.rate_limit_anonymous)
def login(
    request: Request, payload: LoginRequest, db: DbSession
) -> DataResponse[LoginResponse]:
    user = db.scalar(
        select(User).where(User.email == payload.email, User.deleted_at.is_(None))
    )
    # Burn an equivalent bcrypt cost when the user doesn't exist, so response
    # timing does not reveal which emails are registered.
    if user is None:
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
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
        if not _is_email_uniqueness_violation(exc):
            logger.error(
                "Unexpected IntegrityError on user create: %s", exc, exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_USER_CREATE_UNAVAILABLE,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_EMAIL_ALREADY_REGISTERED,
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Failed to create user via admin endpoint: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_USER_CREATE_UNAVAILABLE,
        ) from exc

    db.refresh(user)
    return DataResponse(data=UserRead.model_validate(user))
