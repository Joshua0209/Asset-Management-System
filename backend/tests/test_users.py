from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.user import User, UserRole


class TestListUsers:
    def test_empty_database_returns_empty_list_for_manager(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER, email="mgr@example.com")
        response = client.get("/api/v1/users", headers=auth_headers(manager))
        assert response.status_code == 200
        # Only the manager themselves exists — no other users
        assert len(response.json()["data"]) == 1

    def test_returns_active_users(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER, email="mgr@example.com")
        make_user(role=UserRole.HOLDER, email="alice@example.com", name="Alice")

        response = client.get("/api/v1/users", headers=auth_headers(manager))
        assert response.status_code == 200
        emails = {u["email"] for u in response.json()["data"]}
        assert "alice@example.com" in emails

    def test_excludes_soft_deleted_users(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER, email="mgr@example.com")
        make_user(role=UserRole.HOLDER, email="ghost@example.com", deleted=True)

        response = client.get("/api/v1/users", headers=auth_headers(manager))
        emails = {u["email"] for u in response.json()["data"]}
        assert "ghost@example.com" not in emails

    def test_password_hash_not_in_response(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER, email="mgr@example.com")

        response = client.get("/api/v1/users", headers=auth_headers(manager))
        for user_data in response.json()["data"]:
            assert "password_hash" not in user_data

    def test_users_ordered_by_name(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER, email="z@example.com", name="ZZZ Manager")
        for name, email in [
            ("Charlie", "c@example.com"),
            ("Alice", "a@example.com"),
            ("Bob", "b@example.com"),
        ]:
            make_user(role=UserRole.HOLDER, email=email, name=name)

        response = client.get("/api/v1/users", headers=auth_headers(manager))
        names = [u["name"] for u in response.json()["data"]]
        assert names == sorted(names)

    def test_returns_503_on_db_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER, email="mgr@example.com")
        with patch.object(db_session, "scalars", side_effect=SQLAlchemyError("DB error")):
            response = client.get("/api/v1/users", headers=auth_headers(manager))
        assert response.status_code == 503
