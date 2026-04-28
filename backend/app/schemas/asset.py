from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from app.models.asset import AssetStatus
from app.schemas.common import APIModel


def _today_utc() -> date:
    """Return today's date in UTC to match the project's ISO-8601-UTC convention."""
    return datetime.now(UTC).date()

AssetCategory = Literal[
    "phone",
    "computer",
    "tablet",
    "monitor",
    "printer",
    "network_equipment",
    "other",
]


class AssetCreate(APIModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=120)
    specs: str | None = Field(default=None, max_length=500)
    category: AssetCategory
    supplier: str = Field(min_length=1, max_length=120)
    purchase_date: date
    purchase_amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    location: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=100)
    activation_date: date | None = None
    warranty_expiry: date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> AssetCreate:
        if self.purchase_date > _today_utc():
            raise ValueError("purchase_date must not be in the future")
        if self.warranty_expiry is not None and self.warranty_expiry <= self.purchase_date:
            raise ValueError("warranty_expiry must be after purchase_date")
        return self


class AssetUpdate(APIModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    specs: str | None = Field(default=None, max_length=500)
    category: AssetCategory | None = None
    supplier: str | None = Field(default=None, min_length=1, max_length=120)
    purchase_date: date | None = None
    purchase_amount: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=2)
    location: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=100)
    activation_date: date | None = None
    warranty_expiry: date | None = None
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_consistency(self) -> AssetUpdate:
        non_nullable_fields = {
            "name",
            "model",
            "category",
            "supplier",
            "purchase_date",
            "purchase_amount",
        }
        for field_name in non_nullable_fields:
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if self.purchase_date is not None and self.purchase_date > _today_utc():
            raise ValueError("purchase_date must not be in the future")
        if (
            self.purchase_date is not None
            and self.warranty_expiry is not None
            and self.warranty_expiry <= self.purchase_date
        ):
            raise ValueError("warranty_expiry must be after purchase_date")
        return self


class AssetPersonRead(APIModel):
    id: str
    name: str
    email: str


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
    status: AssetStatus
    responsible_person_id: str | None
    responsible_person: AssetPersonRead | None
    disposal_reason: str | None
    version: int
    created_at: datetime | None
    updated_at: datetime | None
