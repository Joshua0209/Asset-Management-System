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
