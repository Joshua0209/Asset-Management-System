from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.user import User, UserRole


def test_login_enum_lookup_error(db_session: Session) -> None:
    """
    Simulates the issue where the database contains the lowercase enum value ("manager"),
    but the SQLAlchemy model expects the enum name ("MANAGER").
    """
    # 1. Insert a user using raw SQL to bypass SQLAlchemy's Enum parsing on insert.
    # We insert the lowercase value "manager", matching what the Alembic migration would set.
    db_session.execute(
        text(
            """
            INSERT INTO users (
                id, email, password_hash, name, role, department, created_at, updated_at, version
            )
            VALUES (
                'test-id-123', 'admin@example.com', 'hash', 'Admin', 'manager', 'IT',
                '2023-01-01 00:00:00', '2023-01-01 00:00:00', 1
            )
            """
        )
    )
    db_session.commit()

    # 2. Query the user using SQLAlchemy.
    # If the bug is present, this will raise a LookupError when SQLAlchemy tries to
    # map "manager" (from DB) to UserRole, because it defaults to looking for "MANAGER".

    # We expect a LookupError until the bug is fixed.
    # To do TDD properly, we first run this test without pytest.raises to see it fail,
    # then fix it so the final test should pass.
    # Reading the user SHOULD return UserRole.MANAGER.

    user = db_session.query(User).filter_by(email="admin@example.com").first()
    assert user is not None
    assert user.role == UserRole.MANAGER
