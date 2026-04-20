from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User, UserRole


def _make_user(
    session: Session,
    name: str = "Alice",
    email: str = "alice@example.com",
    role: UserRole = UserRole.MANAGER,
    deleted_at: datetime | None = None,
) -> User:
    user = User(
        email=email,
        password_hash="hashed_securely",
        name=name,
        role=role,
        department="IT",
        deleted_at=deleted_at,
    )
    session.add(user)
    session.commit()
    return user


class TestListUsers:
    def test_empty_database_returns_empty_list(self, client: TestClient) -> None:
        response = client.get("/api/v1/users")
        assert response.status_code == 200
        assert response.json() == {"data": []}

    def test_returns_active_users(self, client: TestClient, db_session: Session) -> None:
        _make_user(db_session)

        response = client.get("/api/v1/users")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["email"] == "alice@example.com"

    def test_excludes_soft_deleted_users(self, client: TestClient, db_session: Session) -> None:
        _make_user(db_session, deleted_at=datetime.now(UTC))

        response = client.get("/api/v1/users")
        assert response.json()["data"] == []

    def test_password_hash_not_in_response(self, client: TestClient, db_session: Session) -> None:
        _make_user(db_session)

        response = client.get("/api/v1/users")
        user_data = response.json()["data"][0]
        assert "password_hash" not in user_data

    def test_users_ordered_by_name(self, client: TestClient, db_session: Session) -> None:
        for name, email in [
            ("Charlie", "c@example.com"),
            ("Alice", "a@example.com"),
            ("Bob", "b@example.com"),
        ]:
            _make_user(db_session, name=name, email=email, role=UserRole.HOLDER)

        response = client.get("/api/v1/users")
        names = [u["name"] for u in response.json()["data"]]
        assert names == sorted(names)
