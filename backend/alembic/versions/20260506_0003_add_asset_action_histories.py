"""add asset_action_histories table

Revision ID: 20260506_0003
Revises: 20260504_0002
Create Date: 2026-05-06 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.models.asset_action_history import AssetAction
from app.models.mixins import enum_values

revision = "20260506_0003"
down_revision = "20260504_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_action_histories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column(
            "action",
            sa.Enum(AssetAction, name="asset_action", values_callable=enum_values),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        # The design doc names this column JSONB (Postgres terminology). On
        # MySQL, ``sa.JSON()`` emits the native MySQL JSON type, which is
        # binary-encoded and behaves like JSONB for our purposes (no key
        # ordering, key dedup). On a future Postgres port, switch this to
        # ``postgresql.JSONB`` explicitly — ``sa.JSON()`` on Postgres maps
        # to text JSON, not JSONB.
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
