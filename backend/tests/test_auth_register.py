"""POST /api/v1/auth/register — public, holder-only (Decision A2)."""

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
        "email": "newuser@example.com",
        "password": "Password123",
        "name": "New User",
        "department": "Engineering",
    }
    base.update(overrides)
    return base


class TestRegisterHappyPath:
    def test_returns_201_and_user(self, client: TestClient) -> None:
        response = client.post("/api/v1/auth/register", json=_payload())
        assert response.status_code == 201
        body = response.json()["data"]
        assert body["email"] == "newuser@example.com"
        assert body["name"] == "New User"
        assert body["role"] == "holder"
        assert "id" in body and body["id"]

    def test_persists_user_with_hashed_password(
        self, client: TestClient, db_session: Session
    ) -> None:
        client.post("/api/v1/auth/register", json=_payload())

        user = db_session.scalar(select(User).where(User.email == "newuser@example.com"))
        assert user is not None
        assert user.password_hash != "Password123"
        assert user.password_hash.startswith(("$2a$", "$2b$", "$2y$"))

    def test_response_never_contains_password_hash(self, client: TestClient) -> None:
        response = client.post("/api/v1/auth/register", json=_payload())
        assert "password_hash" not in response.json()["data"]
        assert "password" not in response.json()["data"]


class TestRegisterValidation:
    def test_duplicate_email_returns_409(
        self, client: TestClient, make_user: Callable[..., User]
    ) -> None:
        make_user(email="taken@example.com")
        response = client.post(
            "/api/v1/auth/register", json=_payload(email="taken@example.com")
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_short_password_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/register", json=_payload(password="Pa1")  # 3 chars
        )
        assert response.status_code == 422
        body = response.json()
        # 422s must use the project's error envelope (docs/system-design/12-api-design.md).
        assert body["error"]["code"] == "validation_error"
        assert any(d["field"].endswith("password") for d in body["error"]["details"])

    def test_password_without_digit_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/register", json=_payload(password="NoDigitsHere")
        )
        assert response.status_code == 422

    def test_password_without_letter_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/register", json=_payload(password="12345678")
        )
        assert response.status_code == 422

    def test_malformed_email_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/register", json=_payload(email="not-an-email")
        )
        assert response.status_code == 422

    def test_missing_name_returns_422(self, client: TestClient) -> None:
        bad = _payload()
        del bad["name"]
        response = client.post("/api/v1/auth/register", json=bad)
        assert response.status_code == 422

    def test_malformed_json_returns_422_envelope(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/register",
            content="{",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "validation_error"
        assert body["error"]["details"][0]["code"] == "json_invalid"


class TestRegisterDecisionA2ManagerSuppression:
    def test_client_cannot_self_elevate_to_manager(
        self, client: TestClient, db_session: Session
    ) -> None:
        # Even if a client sends role=manager, public register always creates a holder.
        response = client.post(
            "/api/v1/auth/register", json=_payload(role="manager")
        )
        assert response.status_code == 201
        assert response.json()["data"]["role"] == "holder"

        user = db_session.scalar(select(User).where(User.email == "newuser@example.com"))
        assert user is not None
        assert user.role is UserRole.HOLDER


class TestRegisterDbErrorPaths:
    """Cover the IntegrityError / SQLAlchemyError handlers on POST /auth/register.

    These map raw DBAPI failures into the project's error envelope so the
    public registration endpoint never leaks driver-level tracebacks.
    """

    def test_email_uniqueness_race_at_commit_returns_409(
        self, client: TestClient, db_session: Session
    ) -> None:
        # Reach the IntegrityError handler *with* an email-shaped orig — this
        # is the post-precheck race: two parallel registrations both pass the
        # SELECT-where-email check, only the second one trips the unique index.
        with patch.object(
            db_session,
            "commit",
            side_effect=IntegrityError(
                "INSERT INTO users ...", {}, Exception("Duplicate entry for key email")
            ),
        ):
            response = client.post("/api/v1/auth/register", json=_payload())

        assert response.status_code == 409
        body = response.json()
        assert body["error"]["code"] == "conflict"

    def test_non_email_integrity_error_returns_503(
        self, client: TestClient, db_session: Session
    ) -> None:
        # Any other unique-constraint or FK violation must be surfaced as 503
        # (Decision: do not mask unknown constraint failures as "email taken").
        with patch.object(
            db_session,
            "commit",
            side_effect=IntegrityError(
                "INSERT INTO users ...", {}, Exception("foreign key violation on department")
            ),
        ):
            response = client.post("/api/v1/auth/register", json=_payload())

        assert response.status_code == 503
        body = response.json()["error"]
        assert body["code"] == "service_unavailable"
        # Pins the "Unable to create user" branch (line auth.py:116-119) so a
        # regression that routes this through the generic SQLAlchemyError arm
        # would surface as a message change here rather than passing silently.
        assert body["message"] == "Unable to create user. Please try again later."

    def test_generic_sqlalchemy_error_returns_503(
        self, client: TestClient, db_session: Session
    ) -> None:
        with patch.object(
            db_session, "commit", side_effect=SQLAlchemyError("connection reset")
        ):
            response = client.post("/api/v1/auth/register", json=_payload())

        assert response.status_code == 503
        body = response.json()["error"]
        assert body["code"] == "service_unavailable"
        assert body["message"] == "Unable to register user. Please try again later."
