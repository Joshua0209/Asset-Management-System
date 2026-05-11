"""add composite indexes for multi-dimensional asset search

Revision ID: 20260511_0004
Revises: 20260506_0003
Create Date: 2026-05-11 00:00:00.000000

Phase 2 indexes per docs/system-design/07-database-design.md § Index Strategy.

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
