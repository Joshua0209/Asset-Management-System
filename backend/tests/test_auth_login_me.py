"""POST /api/v1/auth/login + GET /api/v1/auth/me."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.models.user import User, UserRole


class TestLoginHappyPath:
    def test_returns_token_and_user(
        self, client: TestClient, make_user: Callable[..., User]
    ) -> None:
        make_user(email="alice@example.com", password="Password123", name="Alice")

        response = client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "Password123"},
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["token"]
        assert body["expires_at"]
        assert body["user"]["email"] == "alice@example.com"
        assert body["user"]["role"] == "holder"
        # expires_at must parse as an ISO 8601 UTC datetime in the future
        exp = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
        assert exp > datetime.now(UTC)

    def test_token_works_on_auth_me(
        self, client: TestClient, make_user: Callable[..., User]
    ) -> None:
        make_user(email="alice@example.com", password="Password123", name="Alice")

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "Password123"},
        )
        token = login.json()["data"]["token"]

        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["data"]["email"] == "alice@example.com"

    def test_login_response_has_no_password_hash(
        self, client: TestClient, make_user: Callable[..., User]
    ) -> None:
        make_user(email="alice@example.com", password="Password123")
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "Password123"},
        )
        assert "password_hash" not in response.text
        assert "password" not in response.json()["data"]["user"]


class TestLoginAuthenticationFailures:
    def test_wrong_password_returns_401(
        self, client: TestClient, make_user: Callable[..., User]
    ) -> None:
        make_user(email="alice@example.com", password="Password123")
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "WrongPassword9"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"

    def test_unknown_email_returns_401_same_message(
        self, client: TestClient, make_user: Callable[..., User]
    ) -> None:
        # Anti-enumeration: unknown email MUST return the same status + message
        # as wrong password, so an attacker can't probe which emails exist.
        make_user(email="alice@example.com", password="Password123")

        wrong_password = client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "WrongPassword9"},
        )
        unknown_email = client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "WhateverPass9"},
        )

        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json() == unknown_email.json()

    def test_soft_deleted_user_cannot_login(
        self, client: TestClient, make_user: Callable[..., User]
    ) -> None:
        make_user(
            email="ghost@example.com",
            password="Password123",
            deleted=True,
        )
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "Password123"},
        )
        assert response.status_code == 401


class TestLoginValidation:
    def test_malformed_email_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "not-an-email", "password": "Password123"},
        )
        assert response.status_code == 422

    def test_missing_password_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/login", json={"email": "a@example.com"}
        )
        assert response.status_code == 422


class TestAuthMe:
    def test_no_token_returns_401(self, client: TestClient) -> None:
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_valid_token_returns_user(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        u = make_user(email="alice@example.com", role=UserRole.MANAGER)
        response = client.get("/api/v1/auth/me", headers=auth_headers(u))
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["email"] == "alice@example.com"
        assert body["role"] == "manager"
        assert body["id"] == u.id

    def test_expired_token_returns_401(
        self, client: TestClient, make_user: Callable[..., User]
    ) -> None:
        u = make_user()
        token, _ = create_access_token(subject=u.id, role=u.role, expires_minutes=-5)
        response = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401

    def test_me_response_has_no_password_hash(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        u = make_user()
        response = client.get("/api/v1/auth/me", headers=auth_headers(u))
        assert "password_hash" not in response.text
