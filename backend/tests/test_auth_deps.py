"""RBAC dependency matrix — exercises get_current_user / require_manager / require_holder.

Tested indirectly through /api/v1/users, which per api-design §5.1 is Manager-only.
This choice keeps the test black-box and prevents coupling to internal function names.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.models.user import User, UserRole


class TestUsersEndpointRequiresAuth:
    def test_missing_token_returns_401(self, client: TestClient) -> None:
        response = client.get("/api/v1/users")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"

    def test_malformed_authorization_header_returns_401(self, client: TestClient) -> None:
        response = client.get("/api/v1/users", headers={"Authorization": "NotBearer xxx"})
        assert response.status_code == 401

    def test_garbage_token_returns_401(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/users", headers={"Authorization": "Bearer not.a.jwt"}
        )
        assert response.status_code == 401

    def test_expired_token_returns_401(
        self, client: TestClient, make_user: Callable[..., User]
    ) -> None:
        u = make_user(role=UserRole.MANAGER)
        token, _ = create_access_token(subject=u.id, role=u.role, expires_minutes=-1)
        response = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    def test_token_for_nonexistent_user_returns_401(self, client: TestClient) -> None:
        token, _ = create_access_function_safe()
        response = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    def test_token_for_soft_deleted_user_returns_401(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        u = make_user(role=UserRole.MANAGER, deleted=True)
        response = client.get("/api/v1/users", headers=auth_headers(u))
        assert response.status_code == 401


class TestUsersEndpointRequiresManagerRole:
    def test_holder_is_forbidden(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        response = client.get("/api/v1/users", headers=auth_headers(holder))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_manager_is_allowed(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        response = client.get("/api/v1/users", headers=auth_headers(manager))
        assert response.status_code == 200


def create_access_function_safe() -> tuple[str, object]:
    """Mint a token for a UUID that does not exist in any test DB."""
    return create_access_token(
        subject="00000000-0000-0000-0000-000000000000",
        role=UserRole.MANAGER,
    )
