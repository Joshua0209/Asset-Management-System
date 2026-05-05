from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

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
