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
        assert response.json()["meta"] == {
            "total": 2,
            "page": 1,
            "per_page": 20,
            "total_pages": 1,
        }

    def test_filters_by_role_department_and_search_with_pagination(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(
            role=UserRole.MANAGER,
            email="mgr@example.com",
            name="Manager",
            department="IT",
        )
        make_user(
            role=UserRole.HOLDER,
            email="alice@example.com",
            name="Alice Chen",
            department="IT",
        )
        make_user(
            role=UserRole.HOLDER,
            email="alina@example.com",
            name="Alina Wang",
            department="IT",
        )
        make_user(
            role=UserRole.HOLDER,
            email="bob@example.com",
            name="Bob Lin",
            department="Finance",
        )

        response = client.get(
            "/api/v1/users?role=holder&department=IT&q=ali&page=1&per_page=1",
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        body = response.json()
        assert [user["email"] for user in body["data"]] == ["alice@example.com"]
        assert body["meta"] == {
            "total": 2,
            "page": 1,
            "per_page": 1,
            "total_pages": 2,
        }

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

    def test_per_page_above_max_returns_422(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER, email="mgr@example.com")
        response = client.get(
            "/api/v1/users?per_page=101", headers=auth_headers(manager)
        )
        assert response.status_code == 422

    def test_page_zero_returns_422(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER, email="mgr@example.com")
        response = client.get("/api/v1/users?page=0", headers=auth_headers(manager))
        assert response.status_code == 422

    def test_page_past_last_returns_empty_data_with_meta(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER, email="mgr@example.com")
        response = client.get(
            "/api/v1/users?page=999&per_page=1", headers=auth_headers(manager)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []
        assert body["meta"]["page"] == 999
        assert body["meta"]["total"] == 1  # the manager themselves

    def test_invalid_role_filter_returns_422(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER, email="mgr@example.com")
        response = client.get(
            "/api/v1/users?role=not-a-role", headers=auth_headers(manager)
        )
        assert response.status_code == 422

    def test_like_wildcards_in_q_are_escaped(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Regression: a raw `q=%` would have matched every row before LIKE
        # wildcards were escaped in users.py.
        manager = make_user(role=UserRole.MANAGER, email="mgr@example.com")
        make_user(role=UserRole.HOLDER, email="alice@example.com", name="Alice")
        make_user(role=UserRole.HOLDER, email="bob@example.com", name="Bob")

        response = client.get("/api/v1/users?q=%25", headers=auth_headers(manager))

        assert response.status_code == 200
        # No literal % in any name/email, so the result must be empty.
        assert response.json()["data"] == []
