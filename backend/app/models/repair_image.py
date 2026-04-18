from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import utc_now


class RepairImage(Base):
    __tablename__ = "repair_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    repair_request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("repair_requests.id", ondelete="CASCADE"),
        index=True,
    )
    image_url: Mapped[str] = mapped_column(String(255))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    repair_request = relationship("RepairRequest", back_populates="images")
