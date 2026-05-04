from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampVersionMixin


class UserRole(enum.StrEnum):
    HOLDER = "holder"
    MANAGER = "manager"


class User(TimestampVersionMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda obj: [e.value for e in obj])
    )
    department: Mapped[str] = mapped_column(String(100))

    assets = relationship("Asset", back_populates="responsible_person")
    submitted_repair_requests = relationship(
        "RepairRequest",
        back_populates="requester",
        foreign_keys="RepairRequest.requester_id",
    )
    reviewed_repair_requests = relationship(
        "RepairRequest",
        back_populates="reviewer",
        foreign_keys="RepairRequest.reviewer_id",
    )
