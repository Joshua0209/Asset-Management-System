from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.schemas.asset import AssetCreate

_PURCHASE_DATE = date(2026, 1, 1)


def _make_asset(
    session: Session,
    *,
    asset_code: str = "AST-2026-00001",
    status: AssetStatus = AssetStatus.IN_STOCK,
    deleted_at: datetime | None = None,
) -> Asset:
    asset = Asset(
        asset_code=asset_code,
        name="Business Laptop",
        model="Dell Latitude 7440",
        category="Laptop",
        supplier="Dell",
        purchase_date=_PURCHASE_DATE,
        purchase_amount=Decimal("1500.00"),
        location="Taipei HQ",
        department="IT",
        status=status,
        deleted_at=deleted_at,
    )
    session.add(asset)
    session.commit()
    return asset


class TestListAssets:
    def test_empty_database_returns_empty_list(self, client: TestClient) -> None:
        response = client.get("/api/v1/assets")
        assert response.status_code == 200
        assert response.json() == {"data": []}

    def test_returns_active_assets(self, client: TestClient, db_session: Session) -> None:
        _make_asset(db_session)

        response = client.get("/api/v1/assets")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["asset_code"] == "AST-2026-00001"

    def test_excludes_soft_deleted_assets(self, client: TestClient, db_session: Session) -> None:
        _make_asset(db_session, deleted_at=datetime.now(UTC))

        response = client.get("/api/v1/assets")
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_assets_ordered_by_asset_code(self, client: TestClient, db_session: Session) -> None:
        for code in ["AST-2026-00003", "AST-2026-00001", "AST-2026-00002"]:
            _make_asset(db_session, asset_code=code)

        response = client.get("/api/v1/assets")
        codes = [item["asset_code"] for item in response.json()["data"]]
        assert codes == sorted(codes)

    def test_response_does_not_expose_unexpected_fields(
        self, client: TestClient, db_session: Session
    ) -> None:
        _make_asset(db_session)

        response = client.get("/api/v1/assets")
        item = response.json()["data"][0]
        assert "password_hash" not in item

    def test_returns_503_on_db_error(self, client: TestClient, db_session: Session) -> None:
        with patch.object(db_session, "scalars", side_effect=SQLAlchemyError("DB error")):
            response = client.get("/api/v1/assets")
        assert response.status_code == 503


class TestRegisterAsset:
    def test_returns_501_not_implemented(self, client: TestClient) -> None:
        payload = {
            "name": "Business Laptop",
            "model": "Dell Latitude 7440",
            "category": "Laptop",
            "supplier": "Dell",
            "purchase_date": "2026-01-01",
            "purchase_amount": "1500.00",
            "location": "Taipei HQ",
            "department": "IT",
        }
        response = client.post("/api/v1/assets", json=payload)
        assert response.status_code == 501


class TestAssetCreateSchema:
    def test_empty_name_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            AssetCreate(
                name="",
                model="Dell Latitude 7440",
                category="Laptop",
                supplier="Dell",
                purchase_date=_PURCHASE_DATE,
                purchase_amount=Decimal("1500.00"),
                location="Taipei HQ",
                department="IT",
            )

    def test_negative_purchase_amount_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            AssetCreate(
                name="Laptop",
                model="Dell Latitude 7440",
                category="Laptop",
                supplier="Dell",
                purchase_date=_PURCHASE_DATE,
                purchase_amount=Decimal("-1.00"),
                location="Taipei HQ",
                department="IT",
            )

    def test_valid_payload_passes_validation(self) -> None:
        asset = AssetCreate(
            name="Business Laptop",
            model="Dell Latitude 7440",
            category="Laptop",
            supplier="Dell",
            purchase_date=_PURCHASE_DATE,
            purchase_amount=Decimal("1500.00"),
            location="Taipei HQ",
            department="IT",
        )
        assert asset.name == "Business Laptop"
        assert asset.purchase_amount == Decimal("1500.00")
