"""init core tables

Revision ID: 20260417_0001
Revises:
Create Date: 2026-04-17 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260417_0001"
down_revision = None
branch_labels = None
depends_on = None

_USERS_PK = "users.id"


user_role_enum = sa.Enum("holder", "manager", name="user_role")
asset_status_enum = sa.Enum(
    "in_stock",
    "in_use",
    "pending_repair",
    "under_repair",
    "disposed",
    name="asset_status",
)
repair_status_enum = sa.Enum(
    "pending_review",
    "under_repair",
    "completed",
    "rejected",
    name="repair_request_status",
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("role", user_role_enum, nullable=False),
        sa.Column("department", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("specs", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("supplier", sa.String(length=120), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("purchase_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("location", sa.String(length=120), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=False),
        sa.Column("activation_date", sa.Date(), nullable=True),
        sa.Column("warranty_expiry", sa.Date(), nullable=True),
        sa.Column("status", asset_status_enum, nullable=False, server_default="in_stock"),
        sa.Column("responsible_person_id", sa.String(length=36), nullable=True),
        sa.Column("disposal_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["responsible_person_id"], [_USERS_PK], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_code"),
    )
    op.create_index("ix_assets_status", "assets", ["status"], unique=False)
    op.create_index(
        "ix_assets_responsible_person_id",
        "assets",
        ["responsible_person_id"],
        unique=False,
    )

    op.create_table(
        "repair_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("requester_id", sa.String(length=36), nullable=False),
        sa.Column("reviewer_id", sa.String(length=36), nullable=True),
        sa.Column("status", repair_status_enum, nullable=False, server_default="pending_review"),
        sa.Column("fault_description", sa.Text(), nullable=False),
        sa.Column("repair_date", sa.Date(), nullable=True),
        sa.Column("fault_content", sa.Text(), nullable=True),
        sa.Column("repair_plan", sa.Text(), nullable=True),
        sa.Column("repair_cost", sa.Numeric(15, 2), nullable=True),
        sa.Column("repair_vendor", sa.String(length=120), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_id"], [_USERS_PK], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_id"], [_USERS_PK], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_repair_requests_asset_id", "repair_requests", ["asset_id"], unique=False)
    op.create_index(
        "ix_repair_requests_requester_id",
        "repair_requests",
        ["requester_id"],
        unique=False,
    )
    op.create_index("ix_repair_requests_status", "repair_requests", ["status"], unique=False)

    op.create_table(
        "repair_images",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("repair_request_id", sa.String(length=36), nullable=False),
        sa.Column("image_url", sa.String(length=255), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["repair_request_id"], ["repair_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_repair_images_repair_request_id",
        "repair_images",
        ["repair_request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_repair_images_repair_request_id", table_name="repair_images")
    op.drop_table("repair_images")

    op.drop_index("ix_repair_requests_status", table_name="repair_requests")
    op.drop_index("ix_repair_requests_requester_id", table_name="repair_requests")
    op.drop_index("ix_repair_requests_asset_id", table_name="repair_requests")
    op.drop_table("repair_requests")

    op.drop_index("ix_assets_responsible_person_id", table_name="assets")
    op.drop_index("ix_assets_status", table_name="assets")
    op.drop_table("assets")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    repair_status_enum.drop(op.get_bind(), checkfirst=True)
    asset_status_enum.drop(op.get_bind(), checkfirst=True)
    user_role_enum.drop(op.get_bind(), checkfirst=True)
