from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampVersionMixin, enum_values


class AssetStatus(enum.StrEnum):
    IN_STOCK = "in_stock"
    IN_USE = "in_use"
    PENDING_REPAIR = "pending_repair"
    UNDER_REPAIR = "under_repair"
    DISPOSED = "disposed"


class Asset(TimestampVersionMixin, Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(120))
    specs: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100))
    supplier: Mapped[str] = mapped_column(String(120))
    purchase_date: Mapped[date] = mapped_column(Date)
    purchase_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    location: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(100))
    activation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    warranty_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, name="asset_status", values_callable=enum_values),
        default=AssetStatus.IN_STOCK,
    )
    responsible_person_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    disposal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    responsible_person = relationship("User", back_populates="assets")
    repair_requests = relationship("RepairRequest", back_populates="asset")
    action_histories = relationship(
        "AssetActionHistory",
        back_populates="asset",
        order_by="AssetActionHistory.created_at.desc()",
        # viewonly: history rows are inserted only via the audit_log service.
        viewonly=True,
    )
