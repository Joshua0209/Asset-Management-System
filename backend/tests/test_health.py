from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_200_when_db_up(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "up"


@pytest.fixture
def broken_engine() -> Generator[None, None, None]:
    fake_engine = MagicMock()
    fake_engine.connect.side_effect = OperationalError("SELECT 1", {}, Exception("boom"))
    with patch("app.main.engine", fake_engine):
        yield


def test_ready_returns_503_when_db_down(client: TestClient, broken_engine: None) -> None:
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "down"


@pytest.fixture
def pool_exhausted_engine() -> Generator[None, None, None]:
    """Simulate a non-SQLAlchemyError failure mode (M8).

    ``QueuePool``'s ``checkout`` raises a plain ``TimeoutError`` when
    the pool is exhausted — it derives from ``Exception``, NOT from
    ``SQLAlchemyError``. The pre-M8 narrow except clause would have
    let this propagate as 500 instead of 503, which means ALB would
    kill the otherwise-fine container instead of draining the
    unhealthy target.
    """
    fake_engine = MagicMock()
    fake_engine.connect.side_effect = TimeoutError(
        "QueuePool limit of size 5 overflow 10 reached, "
        "connection timed out after 30.00 (Background on this error at: "
        "https://sqlalche.me/e/20/3o7r)"
    )
    with patch("app.main.engine", fake_engine):
        yield


def test_ready_returns_503_on_pool_exhaustion_timeout(
    client: TestClient, pool_exhausted_engine: None
) -> None:
    """Non-SQLAlchemyError exceptions from the engine layer must also
    produce 503, not 500.

    Locks the M8 fix: the readiness probe catches ``Exception``
    broadly on purpose. The prior narrow ``except SQLAlchemyError``
    let pool-exhaustion ``TimeoutError`` propagate to the default
    500 handler — which would trip the ALB into killing the
    container rather than draining the target.
    """
    response = client.get("/ready")
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "down"
