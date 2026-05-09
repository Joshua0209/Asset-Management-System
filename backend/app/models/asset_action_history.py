from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import enum_values, utc_now


class AssetAction(enum.StrEnum):
    # FSM T1 (asset registration → IN_STOCK) is deliberately omitted: the asset
    # row's own ``created_at`` is its audit signal. Only transitions on existing
    # assets land in ``asset_action_histories``.
    ASSIGN = "assign"
    UNASSIGN = "unassign"
    SUBMIT_REPAIR = "submit_repair"
    APPROVE_REPAIR = "approve_repair"
    REJECT_REPAIR = "reject_repair"
    COMPLETE_REPAIR = "complete_repair"
    DISPOSE = "dispose"


class AssetActionHistory(Base):
    """Append-only audit row written atomically with each FSM transition.

    The Python attribute is ``event_metadata`` to avoid colliding with
    SQLAlchemy's reserved ``Base.metadata`` registry; the underlying SQL
    column is ``metadata`` per the design doc.

    No ``version``/``updated_at``/``deleted_at``: these rows are append-only
    (a contributor adding ``TimestampVersionMixin`` would silently break the
    invariant — guarded by ``test_no_updated_or_deleted_or_version_columns``).
    """

    __tablename__ = "asset_action_histories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    actor_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    action: Mapped[AssetAction] = mapped_column(
        Enum(AssetAction, name="asset_action", values_callable=enum_values),
        nullable=False,
    )
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )

    asset = relationship("Asset", back_populates="action_histories")
    actor = relationship("User")
