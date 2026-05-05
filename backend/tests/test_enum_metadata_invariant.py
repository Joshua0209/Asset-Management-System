"""Structural invariant: every SQLAlchemy ``Enum`` column on this metadata
must serialize members by ``.value`` (lowercase), matching the Alembic
migration. A future enum column added without ``values_callable=enum_values``
will trip this check immediately, instead of failing in production on the
first row read.
"""

from __future__ import annotations

from sqlalchemy import Enum

from app.db.base import Base


def test_every_enum_column_maps_by_value() -> None:
    offenders: list[str] = []

    for table in Base.metadata.tables.values():
        for column in table.columns:
            column_type = column.type
            if not isinstance(column_type, Enum) or column_type.enum_class is None:
                continue

            expected = [member.value for member in column_type.enum_class]
            actual = list(column_type.enums)
            if actual != expected:
                offenders.append(
                    f"{table.name}.{column.name}: enum strings={actual!r} expected={expected!r}"
                )

    assert not offenders, (
        "SQLAlchemy Enum columns must use values_callable=enum_values "
        "(see app/models/mixins.py); offenders: " + "; ".join(offenders)
    )
