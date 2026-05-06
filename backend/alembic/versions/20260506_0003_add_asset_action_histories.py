"""add asset_action_histories table

Revision ID: 20260506_0003
Revises: 20260504_0002
Create Date: 2026-05-06 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260506_0003"
down_revision = "20260504_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_action_histories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        # MySQL stores JSON natively; SQLAlchemy JSON is dialect-portable.
        # Design doc calls this JSONB (Postgres term) — JSON is the MySQL
        # equivalent and what SQLAlchemy emits via the abstract type.
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_history_asset", "asset_action_histories", ["asset_id"]
    )
    op.create_index(
        "idx_history_actor", "asset_action_histories", ["actor_id"]
    )
    op.create_index(
        "idx_history_created", "asset_action_histories", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_history_created", table_name="asset_action_histories")
    op.drop_index("idx_history_actor", table_name="asset_action_histories")
    op.drop_index("idx_history_asset", table_name="asset_action_histories")
    op.drop_table("asset_action_histories")
