from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampVersionMixin


class RepairRequestStatus(enum.StrEnum):
    PENDING_REVIEW = "pending_review"
    UNDER_REPAIR = "under_repair"
    COMPLETED = "completed"
    REJECTED = "rejected"


class RepairRequest(TimestampVersionMixin, Base):
    __tablename__ = "repair_requests"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="CASCADE"),
        index=True,
    )
    requester_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    reviewer_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[RepairRequestStatus] = mapped_column(
        Enum(RepairRequestStatus, name="repair_request_status"),
        default=RepairRequestStatus.PENDING_REVIEW,
    )
    fault_description: Mapped[str] = mapped_column(Text)
    repair_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fault_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    repair_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    repair_cost: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    repair_vendor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    asset = relationship("Asset", back_populates="repair_requests")
    requester = relationship(
        "User",
        back_populates="submitted_repair_requests",
        foreign_keys=[requester_id],
    )
    reviewer = relationship(
        "User",
        back_populates="reviewed_repair_requests",
        foreign_keys=[reviewer_id],
    )
    images = relationship(
        "RepairImage",
        back_populates="repair_request",
        cascade="all, delete-orphan",
    )
