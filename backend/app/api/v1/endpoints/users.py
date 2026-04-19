import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ListResponse
from app.schemas.user import UserRead

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=ListResponse[UserRead], summary="List users")
def list_users(db: Session = Depends(get_db)) -> ListResponse[UserRead]:
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
