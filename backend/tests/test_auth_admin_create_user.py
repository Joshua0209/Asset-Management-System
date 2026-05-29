"""POST /api/v1/auth/users — Manager-only create-user (Decision A2 escape hatch)."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.user import User, UserRole


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "email": "created@example.com",
        "password": "Password123",
        "name": "Created User",
        "department": "Ops",
        "location": "Taichung Office",
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
        assert body["department"] == "Ops"
        assert body["location"] == "Taichung Office"

        db_session.expire_all()
        created = db_session.scalar(
            select(User).where(User.email == "created@example.com")
        )
        assert created is not None
        assert created.role is UserRole.MANAGER
        assert created.location == "Taichung Office"

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

    def test_missing_location_returns_422(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        admin = make_user(role=UserRole.MANAGER, email="admin@example.com")
        bad = _payload()
        del bad["location"]
        response = client.post(
            "/api/v1/auth/users",
            json=bad,
            headers=auth_headers(admin),
        )
        assert response.status_code == 422


class TestAdminCreateUserDbErrorPaths:
    """Cover the IntegrityError / SQLAlchemyError handlers on POST /auth/users.

    Parallel to the register-endpoint coverage — admin create user shares the
    same email-collision-vs-other-constraint discrimination logic.
    """

    def test_email_uniqueness_race_at_commit_returns_409(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        admin = make_user(role=UserRole.MANAGER, email="admin@example.com")
        with patch.object(
            db_session,
            "commit",
            side_effect=IntegrityError(
                "INSERT INTO users ...", {}, Exception("Duplicate entry for key email")
            ),
        ):
            response = client.post(
                "/api/v1/auth/users", json=_payload(), headers=auth_headers(admin)
            )

        assert response.status_code == 409
        body = response.json()["error"]
        assert body["code"] == "conflict"
        assert body["message"] == "Email is already registered"

    def test_non_email_integrity_error_returns_503(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        admin = make_user(role=UserRole.MANAGER, email="admin@example.com")
        with patch.object(
            db_session,
            "commit",
            side_effect=IntegrityError(
                "INSERT INTO users ...", {}, Exception("check constraint failed")
            ),
        ):
            response = client.post(
                "/api/v1/auth/users", json=_payload(), headers=auth_headers(admin)
            )

        assert response.status_code == 503
        body = response.json()["error"]
        assert body["code"] == "service_unavailable"
        assert body["message"] == "Unable to create user. Please try again later."

    def test_generic_sqlalchemy_error_returns_503(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        admin = make_user(role=UserRole.MANAGER, email="admin@example.com")
        with patch.object(
            db_session, "commit", side_effect=SQLAlchemyError("connection lost")
        ):
            response = client.post(
                "/api/v1/auth/users", json=_payload(), headers=auth_headers(admin)
            )

        assert response.status_code == 503
        body = response.json()["error"]
        assert body["code"] == "service_unavailable"
        assert body["message"] == "Unable to create user. Please try again later."
