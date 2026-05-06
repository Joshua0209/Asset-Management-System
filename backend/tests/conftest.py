from __future__ import annotations

import os
from collections.abc import Callable, Generator

# Must be set before any app module is imported, since session.py calls get_settings() at load time.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-do-not-use-in-production")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "720")
os.environ.setdefault("REPAIR_UPLOAD_DIR", "/tmp/ams-test-repair-uploads")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402, F401
    asset,
    asset_action_history,
    repair_image,
    repair_request,
    user,
)
from app.models.user import User, UserRole  # noqa: E402

# StaticPool: all connections share the same in-memory SQLite instance within a test.
# Without this, TestClient and get_db would each see a separate empty database.
_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = sessionmaker(
    bind=_TEST_ENGINE, autocommit=False, autoflush=False, class_=Session
)


@pytest.fixture(autouse=True)
def db_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=_TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=_TEST_ENGINE)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


MakeUser = Callable[..., User]


@pytest.fixture
def make_user(db_session: Session) -> MakeUser:
    counter = {"n": 0}

    def _factory(
        *,
        role: UserRole = UserRole.HOLDER,
        email: str | None = None,
        name: str | None = None,
        department: str = "IT",
        password: str = "Password123",
        deleted: bool = False,
    ) -> User:
        counter["n"] += 1
        idx = counter["n"]
        user_obj = User(
            email=email or f"user{idx}@example.com",
            password_hash=hash_password(password),
            name=name or f"User {idx}",
            role=role,
            department=department,
        )
        if deleted:
            from datetime import UTC, datetime

            user_obj.deleted_at = datetime.now(UTC)
        db_session.add(user_obj)
        db_session.commit()
        db_session.refresh(user_obj)
        return user_obj

    return _factory


@pytest.fixture
def auth_headers() -> Callable[[User], dict[str, str]]:
    def _headers(u: User) -> dict[str, str]:
        token, _ = create_access_token(subject=u.id, role=u.role)
        return {"Authorization": f"Bearer {token}"}

    return _headers
