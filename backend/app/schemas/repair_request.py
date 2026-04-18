from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.models.repair_request import RepairRequestStatus
from app.schemas.common import APIModel


class RepairImageRead(APIModel):
    id: str
    image_url: str
    uploaded_at: datetime


class RepairRequestRead(APIModel):
    id: str
    asset_id: str
    requester_id: str
    reviewer_id: str | None
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
