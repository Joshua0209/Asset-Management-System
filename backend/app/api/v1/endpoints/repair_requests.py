from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.repair_request import RepairRequest
from app.schemas.common import ListResponse
from app.schemas.repair_request import RepairRequestRead

router = APIRouter()


@router.get("", response_model=ListResponse[RepairRequestRead], summary="List repair requests")
def list_repair_requests(db: Session = Depends(get_db)) -> ListResponse[RepairRequestRead]:
    requests = db.scalars(
        select(RepairRequest)
        .where(RepairRequest.deleted_at.is_(None))
        .order_by(RepairRequest.created_at.desc())
    ).all()
    return ListResponse(data=[RepairRequestRead.model_validate(item) for item in requests])
