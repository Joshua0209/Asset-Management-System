"""
TDD: verify the composite-index migration exists and is correctly formed.

Structural test — checks migration file content rather than running against
a live database, because the test suite uses SQLite which cannot execute the
MySQL-specific DDL that the other migrations contain.
"""

from __future__ import annotations

import pathlib

MIGRATION_PATH = (
    pathlib.Path(__file__).parent.parent
    / "alembic"
    / "versions"
    / "20260511_0004_add_composite_indexes.py"
)

EXPECTED_INDEXES = [
    "idx_assets_category_status",
    "idx_assets_dept_loc",
    "idx_repair_status_date",
]


def test_migration_file_exists() -> None:
    assert MIGRATION_PATH.exists(), (
        "Migration 20260511_0004_add_composite_indexes.py must exist. "
        "Create it with: alembic revision --rev-id 20260511_0004 -m 'add_composite_indexes'"
    )


def test_migration_creates_all_expected_indexes() -> None:
    source = MIGRATION_PATH.read_text()
    for name in EXPECTED_INDEXES:
        assert name in source, f"Migration must create index {name!r}"


def test_migration_has_no_partial_index_where_clause() -> None:
    """MySQL 8.0 does not support partial indexes (WHERE clause on CREATE INDEX)."""
    source = MIGRATION_PATH.read_text()
    assert "WHERE deleted_at" not in source, (
        "MySQL partial index syntax (WHERE deleted_at IS NULL) is not supported. "
        "Remove the WHERE clause from all op.create_index calls."
    )


def test_migration_has_downgrade_dropping_all_indexes() -> None:
    source = MIGRATION_PATH.read_text()
    assert "op.drop_index" in source, (
        "downgrade() must drop the indexes it creates."
    )
    for name in EXPECTED_INDEXES:
        assert name in source, f"downgrade() must reference index {name!r}"
