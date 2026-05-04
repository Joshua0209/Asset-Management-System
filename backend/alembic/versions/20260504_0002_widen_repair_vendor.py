"""widen repair_vendor to 200 chars

Revision ID: 20260504_0002
Revises: 20260417_0001
Create Date: 2026-05-04 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260504_0002"
down_revision = "20260417_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "repair_requests",
        "repair_vendor",
        existing_type=sa.String(length=120),
        type_=sa.String(length=200),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "repair_requests",
        "repair_vendor",
        existing_type=sa.String(length=200),
        type_=sa.String(length=120),
        existing_nullable=True,
    )
