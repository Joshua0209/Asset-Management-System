import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.asset import Asset
from app.schemas.asset import AssetCreate, AssetRead
from app.schemas.common import DataResponse, ListResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=ListResponse[AssetRead], summary="List assets")
def list_assets(db: Session = Depends(get_db)) -> ListResponse[AssetRead]:
    try:
        assets = db.scalars(
            select(Asset).where(Asset.deleted_at.is_(None)).order_by(Asset.asset_code)
        ).all()
        return ListResponse(data=[AssetRead.model_validate(asset) for asset in assets])
    except SQLAlchemyError as exc:
        logger.error("Failed to list assets: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve assets. Please try again later.",
        ) from exc


@router.post("", response_model=DataResponse[AssetRead], summary="Register an asset")
def register_asset(payload: AssetCreate, db: Session = Depends(get_db)) -> DataResponse[AssetRead]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Asset registration will be available in Week 2.",
    )
