from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field, model_validator

from app.models.repair_request import RepairRequestStatus
from app.schemas.common import APIModel

# Single source of truth for length / digit constraints shared with the
# `repair_requests` table in app/models/repair_request.py. Bumping
# REPAIR_VENDOR_MAX requires an Alembic migration on the matching column.
FAULT_CONTENT_MAX = 1000
REPAIR_PLAN_MAX = 1000
REPAIR_VENDOR_MAX = 200
REJECTION_REASON_MAX = 500
REPAIR_COST_MAX_DIGITS = 15
REPAIR_COST_DECIMAL_PLACES = 2

# Optimistic-lock token: a positive int matching the persisted row version.
RowVersion = Annotated[int, Field(ge=1)]


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


class RepairRequestApprove(APIModel):
    version: RowVersion


class RepairRequestReject(APIModel):
    rejection_reason: str = Field(min_length=1, max_length=REJECTION_REASON_MAX)
    version: RowVersion


class RepairRequestDetailsUpdate(APIModel):
    repair_date: date | None = None
    fault_content: str | None = Field(default=None, max_length=FAULT_CONTENT_MAX)
    repair_plan: str | None = Field(default=None, max_length=REPAIR_PLAN_MAX)
    repair_cost: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=REPAIR_COST_MAX_DIGITS,
        decimal_places=REPAIR_COST_DECIMAL_PLACES,
    )
    repair_vendor: str | None = Field(default=None, max_length=REPAIR_VENDOR_MAX)
    version: RowVersion

    @model_validator(mode="after")
    def _at_least_one_detail_field(self) -> RepairRequestDetailsUpdate:
        # PATCH semantics: a body of just `{"version": N}` would not advance the
        # row version (no dirty columns → no UPDATE), so the client's optimistic
        # lock would silently stay current. Reject up front.
        if self.model_fields_set <= {"version"}:
            raise ValueError("At least one repair-detail field must be provided.")
        return self


class RepairRequestComplete(APIModel):
    repair_date: date
    fault_content: str = Field(min_length=1, max_length=FAULT_CONTENT_MAX)
    repair_plan: str = Field(min_length=1, max_length=REPAIR_PLAN_MAX)
    repair_cost: Decimal = Field(
        ge=0,
        max_digits=REPAIR_COST_MAX_DIGITS,
        decimal_places=REPAIR_COST_DECIMAL_PLACES,
    )
    repair_vendor: str = Field(min_length=1, max_length=REPAIR_VENDOR_MAX)
    version: RowVersion


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
