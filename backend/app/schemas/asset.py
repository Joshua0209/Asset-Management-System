from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.models.asset import AssetStatus
from app.schemas.common import APIModel


class AssetCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=120)
    specs: str | None = None
    category: str = Field(min_length=1, max_length=100)
    supplier: str = Field(min_length=1, max_length=120)
    purchase_date: date
    purchase_amount: Decimal
    location: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=100)
    activation_date: date | None = None
    warranty_expiry: date | None = None


class AssetRead(APIModel):
    id: str
    asset_code: str
    name: str
    model: str
    specs: str | None
    category: str
    supplier: str
    purchase_date: date
    purchase_amount: Decimal
    location: str
    department: str
    activation_date: date | None
    warranty_expiry: date | None
    status: AssetStatus | str
    responsible_person_id: str | None
    disposal_reason: str | None
    version: int
    created_at: datetime | None
    updated_at: datetime | None
