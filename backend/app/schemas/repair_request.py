from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.models.repair_request import RepairRequestStatus
from app.schemas.common import APIModel


class RepairImageRead(APIModel):
    id: str
    url: str = Field(validation_alias="image_url")
    uploaded_at: datetime


class RepairAssetRead(APIModel):
    id: str
    asset_code: str
    name: str


class RepairUserRead(APIModel):
    id: str
    name: str


class RepairRequestCreate(APIModel):
    asset_id: str = Field(min_length=1)
    fault_description: str = Field(min_length=1, max_length=1000)
    version: int | None = Field(default=None, ge=1)


class RepairRequestVersionPayload(APIModel):
    version: int = Field(ge=1)


class RepairRequestReject(APIModel):
    rejection_reason: str = Field(min_length=1, max_length=500)
    version: int = Field(ge=1)


class RepairRequestDetailsUpdate(APIModel):
    repair_date: date | None = None
    fault_content: str | None = Field(default=None, max_length=1000)
    repair_plan: str | None = Field(default=None, max_length=1000)
    repair_cost: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=15,
        decimal_places=2,
    )
    repair_vendor: str | None = Field(default=None, max_length=200)
    version: int = Field(ge=1)


class RepairRequestComplete(APIModel):
    repair_date: date
    fault_content: str = Field(min_length=1, max_length=1000)
    repair_plan: str = Field(min_length=1, max_length=1000)
    repair_cost: Decimal = Field(ge=0, max_digits=15, decimal_places=2)
    repair_vendor: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)


class RepairRequestRead(APIModel):
    id: str
    asset_id: str
    asset: RepairAssetRead
    requester_id: str
    requester: RepairUserRead
    reviewer_id: str | None
    reviewer: RepairUserRead | None
    status: RepairRequestStatus
    fault_description: str
    repair_date: date | None
    fault_content: str | None
    repair_plan: str | None
    repair_cost: Decimal | None
    repair_vendor: str | None
    rejection_reason: str | None
    completed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    images: list[RepairImageRead] = []
