from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole


def test_user_role_loads_when_db_stores_lowercase_value(db_session: Session) -> None:
    """Regression: Alembic creates ``users.role`` with lowercase enum values
    (``'manager'`` / ``'holder'``). Without ``values_callable`` on the SQLAlchemy
    column, hydrating that row raises ``LookupError`` because SQLAlchemy maps
    DB strings to enum *names* (``'MANAGER'``) by default.
    """
    user_id = str(uuid.uuid4())
    # Raw INSERT bypasses the ORM's Enum coercion, reproducing the on-disk
    # state created by alembic/versions/20260417_0001_init_core_tables.py.
    db_session.execute(
        text(
            """
            INSERT INTO users (
                id, email, password_hash, name, role, department, created_at, updated_at, version
            )
            VALUES (
                :id, 'admin@example.com', 'hash', 'Admin', 'manager', 'IT',
                '2023-01-01 00:00:00', '2023-01-01 00:00:00', 1
            )
            """
        ),
        {"id": user_id},
    )
    db_session.commit()

    user = db_session.query(User).filter_by(email="admin@example.com").first()
    assert user is not None
    assert user.role == UserRole.MANAGER


def test_asset_status_loads_when_db_stores_lowercase_value(db_session: Session) -> None:
    """Regression guard for ``assets.status`` mirroring the lowercase Alembic ENUM."""
    asset_id = str(uuid.uuid4())
    db_session.execute(
        text(
            """
            INSERT INTO assets (
                id, asset_code, name, model, category, supplier, purchase_date,
                purchase_amount, location, department, status,
                created_at, updated_at, version
            )
            VALUES (
                :id, 'A-0001', 'Laptop', 'X1', 'IT', 'Acme', '2024-01-01',
                1000.00, 'HQ', 'IT', 'pending_repair',
                '2024-01-01 00:00:00', '2024-01-01 00:00:00', 1
            )
            """
        ),
        {"id": asset_id},
    )
    db_session.commit()

    asset = db_session.query(Asset).filter_by(id=asset_id).first()
    assert asset is not None
    assert asset.status == AssetStatus.PENDING_REPAIR


def test_repair_request_status_loads_when_db_stores_lowercase_value(db_session: Session) -> None:
    """Regression guard for ``repair_requests.status`` mirroring the lowercase Alembic ENUM."""
    user_id = str(uuid.uuid4())
    asset_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())

    db_session.add(
        User(
            id=user_id,
            email="requester@example.com",
            password_hash="hash",
            name="Requester",
            role=UserRole.HOLDER,
            department="IT",
        )
    )
    db_session.add(
        Asset(
            id=asset_id,
            asset_code="A-0002",
            name="Laptop",
            model="X1",
            category="IT",
            supplier="Acme",
            purchase_date=date(2024, 1, 1),
            purchase_amount=1000,
            location="HQ",
            department="IT",
            status=AssetStatus.IN_USE,
            responsible_person_id=user_id,
        )
    )
    db_session.commit()

    db_session.execute(
        text(
            """
            INSERT INTO repair_requests (
                id, asset_id, requester_id, status, fault_description,
                created_at, updated_at, version
            )
            VALUES (
                :id, :asset_id, :requester_id, 'under_repair', 'screen broken',
                '2024-01-01 00:00:00', '2024-01-01 00:00:00', 1
            )
            """
        ),
        {"id": request_id, "asset_id": asset_id, "requester_id": user_id},
    )
    db_session.commit()

    request = db_session.query(RepairRequest).filter_by(id=request_id).first()
    assert request is not None
    assert request.status == RepairRequestStatus.UNDER_REPAIR
