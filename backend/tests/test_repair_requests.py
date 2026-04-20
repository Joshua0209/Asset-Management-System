from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole

_PURCHASE_DATE = date(2026, 1, 1)


def _make_user(session: Session, name: str = "Holder", role: UserRole = UserRole.HOLDER) -> User:
    user = User(
        email=f"{name.lower().replace(' ', '')}@example.com",
        password_hash="$2b$12$placeholder_hash_for_tests",  # NOSONAR
        name=name,
        role=role,
        department="IT",
    )
    session.add(user)
    session.flush()
    return user


def _make_asset(session: Session, holder: User | None = None) -> Asset:
    asset = Asset(
        asset_code="AST-2026-00001",
        name="Business Laptop",
        model="Dell Latitude 7440",
        category="Laptop",
        supplier="Dell",
        purchase_date=_PURCHASE_DATE,
        purchase_amount=Decimal("1500.00"),
        location="Taipei HQ",
        department="IT",
        status=AssetStatus.IN_USE if holder else AssetStatus.IN_STOCK,
        responsible_person_id=holder.id if holder else None,
    )
    session.add(asset)
    session.flush()
    return asset


class TestListRepairRequests:
    def test_empty_database_returns_empty_list(self, client: TestClient) -> None:
        response = client.get("/api/v1/repair-requests")
        assert response.status_code == 200
        assert response.json() == {"data": []}

    def test_returns_repair_requests_with_images_field(
        self, client: TestClient, db_session: Session
    ) -> None:
        holder = _make_user(db_session)
        asset = _make_asset(db_session, holder)
        rr = RepairRequest(
            asset_id=asset.id,
            requester_id=holder.id,
            status=RepairRequestStatus.PENDING_REVIEW,
            fault_description="Screen flickers.",
        )
        db_session.add(rr)
        db_session.commit()

        response = client.get("/api/v1/repair-requests")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert "images" in data[0]
        assert data[0]["images"] == []

    def test_excludes_soft_deleted_repair_requests(
        self, client: TestClient, db_session: Session
    ) -> None:
        holder = _make_user(db_session)
        asset = _make_asset(db_session, holder)
        rr = RepairRequest(
            asset_id=asset.id,
            requester_id=holder.id,
            status=RepairRequestStatus.PENDING_REVIEW,
            fault_description="Deleted request.",
            deleted_at=datetime.now(UTC),
        )
        db_session.add(rr)
        db_session.commit()

        response = client.get("/api/v1/repair-requests")
        assert response.json()["data"] == []

    def test_returns_503_on_db_error(self, client: TestClient, db_session: Session) -> None:
        with patch.object(db_session, "scalars", side_effect=SQLAlchemyError("DB error")):
            response = client.get("/api/v1/repair-requests")
        assert response.status_code == 503

    def test_results_ordered_newest_first(self, client: TestClient, db_session: Session) -> None:
        holder = _make_user(db_session)
        asset = _make_asset(db_session, holder)

        now = datetime.now(UTC)
        for i, fault in enumerate(["Issue A", "Issue B", "Issue C"]):
            rr = RepairRequest(
                asset_id=asset.id,
                requester_id=holder.id,
                status=RepairRequestStatus.PENDING_REVIEW,
                fault_description=fault,
            )
            db_session.add(rr)
            db_session.flush()
            rr.created_at = now - __import__("datetime").timedelta(hours=i)
        db_session.commit()

        response = client.get("/api/v1/repair-requests")
        timestamps = [item["created_at"] for item in response.json()["data"]]
        assert timestamps == sorted(timestamps, reverse=True)
