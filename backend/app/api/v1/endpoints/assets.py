from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.asset import Asset
from app.schemas.asset import AssetCreate, AssetRead
from app.schemas.common import DataResponse, ListResponse

router = APIRouter()


@router.get("", response_model=ListResponse[AssetRead], summary="List assets")
def list_assets(db: Session = Depends(get_db)) -> ListResponse[AssetRead]:
    assets = db.scalars(
        select(Asset).where(Asset.deleted_at.is_(None)).order_by(Asset.asset_code)
    ).all()
    return ListResponse(data=[AssetRead.model_validate(asset) for asset in assets])


@router.post("", response_model=DataResponse[AssetRead], summary="Register an asset")
def register_asset(payload: AssetCreate) -> DataResponse[AssetRead]:
    # Week 1 scaffold: contract first, service logic follows in Week 2.
    asset = AssetRead(
        id="pending-implementation",
        asset_code="AST-0000",
        name=payload.name,
        model=payload.model,
        specs=payload.specs,
        category=payload.category,
        supplier=payload.supplier,
        purchase_date=payload.purchase_date,
        purchase_amount=payload.purchase_amount,
        location=payload.location,
        department=payload.department,
        activation_date=payload.activation_date,
        warranty_expiry=payload.warranty_expiry,
        status="in_stock",
        responsible_person_id=None,
        disposal_reason=None,
        version=1,
        created_at=None,
        updated_at=None,
    )
    return DataResponse(data=asset)
