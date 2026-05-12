"""add composite indexes for multi-dimensional asset search

Revision ID: 20260511_0004
Revises: 20260506_0003
Create Date: 2026-05-11 00:00:00.000000

Phase 2 indexes per docs/system-design/07-database-design.md § Index Strategy.

Index shape — these are leftmost-prefix composites; the InnoDB optimizer uses
them only when the first column appears in the predicate. Concretely:
  - idx_assets_category_status helps queries filtering by `category`
    (alone or combined with `status`). `status`-only queries continue to
    use the single-column ix_assets_status from migration 0001.
  - idx_assets_dept_loc helps queries filtering by `department`
    (alone or combined with `location`). `location`-only queries fall back
    to a full scan today; if those become hot, add ix_assets_location later.
  - idx_repair_status_date covers the canonical repair-list query in
    backend/app/api/v1/endpoints/repair_requests.py — status filter plus
    the default `-created_at` sort.

Online-safe on MySQL 8.0: InnoDB defaults to ALGORITHM=INPLACE, LOCK=NONE
for adding secondary indexes, so applying this migration does not block
concurrent writes during deployment.

Note: MySQL 8.0 does not support partial indexes (CREATE INDEX ... WHERE clause),
so the soft-delete filter from the design doc is omitted here.
Queries already apply the deleted_at IS NULL condition at query time, so the
index remains effective — soft-deleted rows are included in the index at a
small storage cost but are never returned to callers.
"""

from __future__ import annotations

from alembic import op

revision = "20260511_0004"
down_revision = "20260506_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_assets_category_status",
        "assets",
        ["category", "status"],
    )
    op.create_index(
        "idx_assets_dept_loc",
        "assets",
        ["department", "location"],
    )
    op.create_index(
        "idx_repair_status_date",
        "repair_requests",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_repair_status_date", table_name="repair_requests")
    op.drop_index("idx_assets_dept_loc", table_name="assets")
    op.drop_index("idx_assets_category_status", table_name="assets")
