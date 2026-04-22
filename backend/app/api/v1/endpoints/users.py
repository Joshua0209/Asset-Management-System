import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import ManagerUser
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ListResponse
from app.schemas.user import UserRead

logger = logging.getLogger(__name__)
router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", summary="List users")
def list_users(db: DbSession, _current: ManagerUser) -> ListResponse[UserRead]:
    try:
        users = db.scalars(
            select(User).where(User.deleted_at.is_(None)).order_by(User.name)
        ).all()
        return ListResponse(data=[UserRead.model_validate(user) for user in users])
    except SQLAlchemyError as exc:
        logger.error("Failed to list users: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve users. Please try again later.",
        ) from exc
