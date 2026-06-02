"""Regression tests for UTC-aware datetime serialization.

MySQL ``DATETIME`` columns drop timezone info, so datetimes read back from the
DB are naive even though ``utc_now()`` writes them as UTC. A naive datetime
serializes to JSON without an offset, which ``new Date(...)`` on the frontend
parses as *local* time — rendering a UTC instant 8 hours early in Taipei. The
``UtcDatetime`` annotated type (app/schemas/common.py) stamps UTC so the wire
format always carries an explicit offset.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app.schemas.common import _ensure_utc
from app.schemas.repair_request import RepairImageRead


def test_ensure_utc_stamps_naive_datetime() -> None:
    # Arrange: a naive datetime, as read back from a MySQL DATETIME column.
    naive = datetime(2026, 6, 2, 12, 42, 11)

    # Act
    result = _ensure_utc(naive)

    # Assert: now UTC-aware, same wall-clock reading.
    assert result.tzinfo is not None
    assert result.utcoffset() == timedelta(0)
    assert result.replace(tzinfo=None) == naive


def test_ensure_utc_converts_aware_non_utc_to_utc() -> None:
    # Arrange: 20:42 in Taipei (UTC+8) is 12:42 UTC.
    taipei = datetime(2026, 6, 2, 20, 42, 11, tzinfo=timezone(timedelta(hours=8)))

    # Act
    result = _ensure_utc(taipei)

    # Assert
    assert result.utcoffset() == timedelta(0)
    assert result == datetime(2026, 6, 2, 12, 42, 11, tzinfo=UTC)


def test_read_schema_serializes_naive_datetime_with_offset() -> None:
    # Arrange: simulate the ORM handing back a naive UTC datetime.
    class _Row:
        id = "img-1"
        uploaded_at = datetime(2026, 6, 2, 12, 42, 11)

    # Act
    dumped = RepairImageRead.model_validate(_Row()).model_dump(mode="json")

    # Assert: the JSON string carries an explicit UTC marker (Pydantic emits
    # the ``Z`` form for UTC), so the frontend converts it to local time
    # instead of treating a naive string as already-local.
    assert dumped["uploaded_at"] == "2026-06-02T12:42:11Z"
