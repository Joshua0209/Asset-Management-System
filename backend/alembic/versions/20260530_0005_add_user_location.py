"""add user location

Revision ID: 20260530_0005
Revises: 20260511_0004
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260530_0005"
down_revision = "20260506_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("location", sa.String(length=120), nullable=False, server_default="Unknown"),
    )
    op.alter_column("users", "location", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "location")
