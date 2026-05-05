from __future__ import annotations

import enum
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


def enum_values(obj: type[enum.Enum]) -> Sequence[str]:
    """SQLAlchemy ``values_callable`` that maps by ``.value`` instead of ``.name``.

    Alembic migrations create ``ENUM(...)`` columns from the lowercase Python enum
    values; without this callable SQLAlchemy persists/looks-up by the uppercase
    enum *name* and raises ``LookupError`` on read.
    """
    return [e.value for e in obj]


class TimestampVersionMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, object]:
        return {"version_id_col": cls.version}
