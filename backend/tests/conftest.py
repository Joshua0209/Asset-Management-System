from __future__ import annotations

import os
from collections.abc import Callable, Generator
from typing import Any

# ---------------------------------------------------------------------------
# IMPORT-ORDER INVARIANT — DO NOT IMPORT ANY ``app.*`` MODULE ABOVE THIS LINE.
#
# `app/core/config.py::get_settings` is `@lru_cache`-decorated and
# `app/db/session.py` calls it at module load time. Once any `app.*` module
# is imported, those env-var values are baked into the cache and later
# `os.environ.setdefault(...)` calls become silent no-ops (the cache already
# has the unset defaults). The block below MUST run before the app imports
# at the bottom of this file. If you add a new import, put it AFTER the
# `os.environ.setdefault` block, or invalidate `get_settings.cache_clear()`
# explicitly.
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-do-not-use-in-production")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "720")
os.environ.setdefault("REPAIR_UPLOAD_DIR", "/tmp/ams-test-repair-uploads")
# Bootstrap credentials are now required (no defaults in Settings) so a
# Secrets Manager injection failure in production fails loud instead of
# seeding `admin@example.com` / `ChangeMe123`. The test suite supplies
# its own dummies via the same env-var path production uses.
os.environ.setdefault("BOOTSTRAP_MANAGER_EMAIL", "bootstrap@test.example")
os.environ.setdefault("BOOTSTRAP_MANAGER_PASSWORD", "TestPassword123")  # noqa: S105

# Rate limiting — disabled by default so the existing test suite is not
# timing-sensitive. Tests that *want* limits flip
# ``app.state.limiter.enabled = True`` via the ``enabled_limiter`` fixture
# (see tests/test_rate_limit.py). Tight numeric limits are pre-configured so
# the per-test 429s trigger in only a handful of requests rather than 30+.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_ANONYMOUS", "3/minute")
os.environ.setdefault("RATE_LIMIT_AUTHENTICATED", "5/minute")
os.environ.setdefault("RATE_LIMIT_IMAGES", "10/minute")
os.environ.setdefault("RATE_LIMIT_BEACON", "3/minute")

# ---------------------------------------------------------------------------
# Safe to import app.* below this line — env is now configured.
# ---------------------------------------------------------------------------
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


@pytest.fixture(autouse=True)
def _reset_trace_context_warned_sentinel() -> Generator[None, None, None]:
    """Reset ``observability._TRACE_CONTEXT_WARNED`` per test.

    The structlog processor stamps the active span's trace_id on every
    log record. If the span-lookup raises (broken OTel install, SDK
    drift), it logs one warning and silences subsequent failures via
    this module-level sentinel — without per-test reset, the first
    test in a pytest session that exercises the failure path "uses
    up" the warning quota for the entire process, and every later
    test that depends on seeing the warning silently passes without
    it.

    ``test_observability.py`` has its own module-scoped autouse
    fixture that also resets this flag (alongside several other OTel
    install flags) — but it doesn't apply across files. Tests in
    ``test_client_error_beacon.py`` etc. that incidentally drive the
    structlog processor would otherwise share state with whatever
    ran first. This fixture closes the cross-file gap.

    Cheap: a module-level attribute write twice per test.
    """
    from app.core import observability as obs
    obs._TRACE_CONTEXT_WARNED = False
    yield
    obs._TRACE_CONTEXT_WARNED = False


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
        location: str = "Taipei HQ",
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
            location=location,
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


@pytest.fixture
def scalar_skip_auth(db_session: Session) -> Callable[[BaseException], Callable[..., Any]]:
    """Factory that builds a ``db.scalar`` side_effect with auth-pass-through.

    Endpoints that themselves call ``db.scalar`` share the call with
    ``get_current_user`` (which always issues the first scalar to resolve
    the bearer token). Patching ``db.scalar`` globally would therefore 401
    before the endpoint's own scalar ever runs — masking the branch under
    test. This factory returns a side_effect that lets the first scalar
    pass through (the auth lookup) and raises ``exc`` on every subsequent
    call (the endpoint's own scalar).

    The pattern was previously duplicated across test_assets.py,
    test_repair_requests.py, and test_images.py. Centralising it here
    keeps the auth-call-count invariant in one place.
    """
    real_scalar = db_session.scalar

    def _build(exc: BaseException) -> Callable[..., Any]:
        calls = {"n": 0}

        def _side_effect(*args: Any, **kwargs: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                return real_scalar(*args, **kwargs)
            raise exc

        return _side_effect

    return _build
