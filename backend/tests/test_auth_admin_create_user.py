"""POST /api/v1/auth/users — Manager-only create-user (Decision A2 escape hatch)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserRole


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "email": "created@example.com",
        "password": "Password123",
        "name": "Created User",
        "department": "Ops",
        "role": "manager",
    }
    base.update(overrides)
    return base


class TestAdminCreateUser:
    def test_no_token_returns_401(self, client: TestClient) -> None:
        response = client.post("/api/v1/auth/users", json=_payload())
        assert response.status_code == 401

    def test_holder_cannot_create_user(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER, email="h@example.com")
        response = client.post(
            "/api/v1/auth/users", json=_payload(), headers=auth_headers(holder)
        )
        assert response.status_code == 403

    def test_manager_can_create_manager(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        admin = make_user(role=UserRole.MANAGER, email="admin@example.com")
        response = client.post(
            "/api/v1/auth/users", json=_payload(), headers=auth_headers(admin)
        )
        assert response.status_code == 201
        body = response.json()["data"]
        assert body["email"] == "created@example.com"
        assert body["role"] == "manager"

        db_session.expire_all()
        created = db_session.scalar(
            select(User).where(User.email == "created@example.com")
        )
        assert created is not None
        assert created.role is UserRole.MANAGER

    def test_manager_can_create_holder(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        admin = make_user(role=UserRole.MANAGER, email="admin@example.com")
        response = client.post(
            "/api/v1/auth/users",
            json=_payload(role="holder"),
            headers=auth_headers(admin),
        )
        assert response.status_code == 201
        assert response.json()["data"]["role"] == "holder"

    def test_duplicate_email_returns_409(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        admin = make_user(role=UserRole.MANAGER, email="admin@example.com")
        make_user(email="taken@example.com")
        response = client.post(
            "/api/v1/auth/users",
            json=_payload(email="taken@example.com"),
            headers=auth_headers(admin),
        )
        assert response.status_code == 409

    def test_invalid_role_returns_422(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        admin = make_user(role=UserRole.MANAGER, email="admin@example.com")
        response = client.post(
            "/api/v1/auth/users",
            json=_payload(role="superuser"),
            headers=auth_headers(admin),
        )
        assert response.status_code == 422

    def test_weak_password_returns_422(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        admin = make_user(role=UserRole.MANAGER, email="admin@example.com")
        response = client.post(
            "/api/v1/auth/users",
            json=_payload(password="short"),
            headers=auth_headers(admin),
        )
        assert response.status_code == 422
