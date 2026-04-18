from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ListResponse
from app.schemas.user import UserRead

router = APIRouter()


@router.get("", response_model=ListResponse[UserRead], summary="List users")
def list_users(db: Session = Depends(get_db)) -> ListResponse[UserRead]:
    users = db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.name)).all()
    return ListResponse(data=[UserRead.model_validate(user) for user in users])
