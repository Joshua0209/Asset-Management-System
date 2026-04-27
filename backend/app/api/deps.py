"""FastAPI auth dependencies.

Layered so each protected route can declare its requirement at the signature:
    from app.api.deps import CurrentUser, ManagerUser, HolderUser

    def list_assets(user: ManagerUser) -> ...

FastAPI de-duplicates identical dependency functions within a single request,
so composing require_manager on get_current_user has zero extra cost.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole

# auto_error=False: we shape the 401 ourselves;
# FastAPI's default returns plain 403 when the header is missing.
_bearer_scheme = HTTPBearer(auto_error=False, bearerFormat="JWT")

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="unauthorized",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _UNAUTHORIZED
    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise _UNAUTHORIZED from exc

    user = db.scalar(
        select(User).where(User.id == payload.sub, User.deleted_at.is_(None))
    )
    if user is None:
        raise _UNAUTHORIZED
    return user


def require_manager(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role is not UserRole.MANAGER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return user


def require_holder(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role is not UserRole.HOLDER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
ManagerUser = Annotated[User, Depends(require_manager)]
HolderUser = Annotated[User, Depends(require_holder)]
