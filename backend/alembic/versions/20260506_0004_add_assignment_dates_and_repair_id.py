"""add assignment dates and repair_id

Revision ID: 20260506_0004
Revises: 20260511_0004
Create Date: 2026-05-06 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260506_0004"
# Chained after 20260511_0004 (composite indexes, merged via PR #46) to keep
# the alembic tree single-headed. Both migrations originally branched from
# 20260506_0003, so the second-to-merge has to re-chain.
down_revision = "20260511_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("assignment_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column("unassignment_date", sa.Date(), nullable=True),
    )

    # Add `repair_id` in three steps so the migration works on tables that
    # already contain repair requests:
    #   1. add the column nullable (so existing rows survive)
    #   2. backfill deterministic ids: REP-{year(created_at)}-{seq:05d},
    #      sequence resetting per year and ordered by created_at
    #   3. promote to NOT NULL + UNIQUE
    op.add_column(
        "repair_requests",
        sa.Column("repair_id", sa.String(length=32), nullable=True),
    )

    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "mysql":
        bind.exec_driver_sql(
            """
            UPDATE repair_requests AS rr
            JOIN (
                SELECT
                    id,
                    CONCAT(
                        'REP-',
                        YEAR(created_at),
                        '-',
                        LPAD(
                            ROW_NUMBER() OVER (
                                PARTITION BY YEAR(created_at)
                                ORDER BY created_at, id
                            ),
                            5,
                            '0'
                        )
                    ) AS new_repair_id
                FROM repair_requests
            ) AS numbered
              ON numbered.id = rr.id
            SET rr.repair_id = numbered.new_repair_id
            """
        )
    else:
        # SQLite/postgres-friendly fallback used in tests and local sqlite.
        bind.exec_driver_sql(
            """
            WITH numbered AS (
                SELECT
                    id,
                    CAST(strftime('%Y', created_at) AS INTEGER) AS yr,
                    ROW_NUMBER() OVER (
                        PARTITION BY CAST(strftime('%Y', created_at) AS INTEGER)
                        ORDER BY created_at, id
                    ) AS seq
                FROM repair_requests
            )
            UPDATE repair_requests
               SET repair_id = (
                    SELECT 'REP-' || numbered.yr || '-' ||
                           substr('00000' || numbered.seq, -5)
                      FROM numbered
                     WHERE numbered.id = repair_requests.id
                )
            """
        )

    op.alter_column(
        "repair_requests",
        "repair_id",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_repair_requests_repair_id",
        "repair_requests",
        ["repair_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_repair_requests_repair_id",
        "repair_requests",
        type_="unique",
    )
    op.drop_column("repair_requests", "repair_id")
    op.drop_column("assets", "unassignment_date")
    op.drop_column("assets", "assignment_date")
