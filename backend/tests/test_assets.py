from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole
from app.schemas.asset import AssetCreate

_PURCHASE_DATE = date(2026, 1, 1)


def _make_asset(
    session: Session,
    *,
    asset_code: str = "AST-2026-00001",
    status: AssetStatus = AssetStatus.IN_STOCK,
    deleted_at: datetime | None = None,
    name: str = "Business Laptop",
    model: str = "Dell Latitude 7440",
    category: str = "computer",
    department: str = "IT",
    location: str = "Taipei HQ",
    responsible_person_id: str | None = None,
    warranty_expiry: date | None = None,
) -> Asset:
    asset = Asset(
        asset_code=asset_code,
        name=name,
        model=model,
        category=category,
        supplier="Dell",
        purchase_date=_PURCHASE_DATE,
        purchase_amount=Decimal("1500.00"),
        location=location,
        department=department,
        status=status,
        deleted_at=deleted_at,
        responsible_person_id=responsible_person_id,
        warranty_expiry=warranty_expiry,
    )
    session.add(asset)
    session.commit()
    return asset


def _make_repair_request(
    session: Session,
    *,
    asset: Asset,
    requester: User,
    status: RepairRequestStatus = RepairRequestStatus.PENDING_REVIEW,
    deleted_at: datetime | None = None,
    fault_description: str = "Screen flickering.",
) -> RepairRequest:
    repair_request = RepairRequest(
        asset_id=asset.id,
        requester_id=requester.id,
        status=status,
        fault_description=fault_description,
        deleted_at=deleted_at,
    )
    session.add(repair_request)
    session.commit()
    return repair_request


class TestListAssets:
    def test_empty_database_returns_empty_list(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        response = client.get("/api/v1/assets", headers=auth_headers(manager))
        assert response.status_code == 200
        assert response.json() == {
            "data": [],
            "meta": {"total": 0, "page": 1, "per_page": 20, "total_pages": 0},
        }

    def test_returns_active_assets(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER, name="Alice")
        _make_asset(db_session, responsible_person_id=holder.id)

        response = client.get("/api/v1/assets?sort=asset_code", headers=auth_headers(manager))
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["asset_code"] == "AST-2026-00001"
        assert data[0]["responsible_person"] == {
            "id": holder.id,
            "name": "Alice",
            "email": holder.email,
        }

    def test_excludes_soft_deleted_assets(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        _make_asset(db_session, deleted_at=datetime.now(UTC))

        response = client.get("/api/v1/assets", headers=auth_headers(manager))
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_assets_ordered_by_asset_code(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        for code in ["AST-2026-00003", "AST-2026-00001", "AST-2026-00002"]:
            _make_asset(db_session, asset_code=code)

        response = client.get("/api/v1/assets?sort=asset_code", headers=auth_headers(manager))
        codes = [item["asset_code"] for item in response.json()["data"]]
        assert codes == sorted(codes)

    def test_paginates_and_filters_assets(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        _make_asset(db_session, asset_code="AST-2026-00001", category="computer")
        _make_asset(db_session, asset_code="AST-2026-00002", category="computer")
        _make_asset(db_session, asset_code="AST-2026-00003", category="monitor")

        response = client.get(
            "/api/v1/assets?page=2&per_page=1&category=computer&sort=asset_code",
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        body = response.json()
        assert [item["asset_code"] for item in body["data"]] == ["AST-2026-00002"]
        assert body["meta"] == {"total": 2, "page": 2, "per_page": 1, "total_pages": 2}

    def test_searches_assets(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        _make_asset(db_session, asset_code="AST-2026-00001", name="Business Laptop")
        _make_asset(db_session, asset_code="AST-2026-00002", name="Conference Monitor")

        response = client.get("/api/v1/assets?q=laptop", headers=auth_headers(manager))

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["asset_code"] == "AST-2026-00001"

    def test_holder_cannot_list_assets(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        response = client.get("/api/v1/assets", headers=auth_headers(holder))
        assert response.status_code == 403

    def test_holder_lists_own_assets(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        other_holder = make_user(role=UserRole.HOLDER)
        _make_asset(db_session, asset_code="AST-2026-00001", responsible_person_id=holder.id)
        _make_asset(db_session, asset_code="AST-2026-00002", responsible_person_id=other_holder.id)

        response = client.get("/api/v1/assets/mine?sort=asset_code", headers=auth_headers(holder))

        assert response.status_code == 200
        data = response.json()["data"]
        assert [item["asset_code"] for item in data] == ["AST-2026-00001"]

    def test_response_does_not_expose_unexpected_fields(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        _make_asset(db_session)

        response = client.get("/api/v1/assets", headers=auth_headers(manager))
        item = response.json()["data"][0]
        assert "password_hash" not in item

    def test_returns_503_on_db_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        with patch.object(db_session, "scalars", side_effect=SQLAlchemyError("DB error")):
            response = client.get("/api/v1/assets", headers=auth_headers(manager))
        assert response.status_code == 503

    def test_unsupported_sort_field_returns_422(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        response = client.get(
            "/api/v1/assets?sort=password_hash", headers=auth_headers(manager)
        )
        assert response.status_code == 422

    def test_manager_cannot_use_holder_only_mine_endpoint(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        response = client.get("/api/v1/assets/mine", headers=auth_headers(manager))
        assert response.status_code == 403

    def test_soft_deleted_holder_is_hidden_from_responsible_person(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER, name="Soft Deleted", deleted=True)
        _make_asset(db_session, responsible_person_id=holder.id)

        response = client.get("/api/v1/assets", headers=auth_headers(manager))
        assert response.status_code == 200
        item = response.json()["data"][0]
        assert item["responsible_person"] is None


class TestRegisterAsset:
    def test_registers_asset(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        payload = {
            "name": "Business Laptop",
            "model": "Dell Latitude 7440",
            "category": "computer",
            "supplier": "Dell",
            "purchase_date": "2026-01-01",
            "purchase_amount": "1500.00",
            "location": "Taipei HQ",
            "department": "IT",
        }
        response = client.post("/api/v1/assets", json=payload, headers=auth_headers(manager))
        assert response.status_code == 201
        assert response.headers["location"].startswith("/api/v1/assets/")
        data = response.json()["data"]
        assert data["asset_code"] == "AST-2026-00001"
        assert data["status"] == "in_stock"
        assert data["responsible_person_id"] is None

    def test_registers_asset_without_optional_location_department(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        payload = {
            "name": "Business Laptop",
            "model": "Dell Latitude 7440",
            "category": "computer",
            "supplier": "Dell",
            "purchase_date": "2026-01-01",
            "purchase_amount": "1500.00",
        }

        response = client.post("/api/v1/assets", json=payload, headers=auth_headers(manager))

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["location"] == ""
        assert data["department"] == ""

    def test_retries_when_generated_asset_code_conflicts(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        _make_asset(db_session, asset_code="AST-2026-00001")
        payload = {
            "name": "Business Laptop",
            "model": "Dell Latitude 7440",
            "category": "computer",
            "supplier": "Dell",
            "purchase_date": "2026-01-01",
            "purchase_amount": "1500.00",
            "location": "Taipei HQ",
            "department": "IT",
        }

        with patch(
            "app.api.v1.endpoints.assets._next_asset_code",
            side_effect=["AST-2026-00001", "AST-2026-00002"],
        ):
            response = client.post("/api/v1/assets", json=payload, headers=auth_headers(manager))

        assert response.status_code == 201
        assert response.json()["data"]["asset_code"] == "AST-2026-00002"

    def test_holder_cannot_register_asset(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        response = client.post(
            "/api/v1/assets",
            json={
                "name": "Business Laptop",
                "model": "Dell Latitude 7440",
                "category": "computer",
                "supplier": "Dell",
                "purchase_date": "2026-01-01",
                "purchase_amount": "1500.00",
                "location": "Taipei HQ",
                "department": "IT",
            },
            headers=auth_headers(holder),
        )
        assert response.status_code == 403

    def test_returns_409_after_retry_exhaustion(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        _make_asset(db_session, asset_code="AST-2026-00001")
        payload = {
            "name": "Business Laptop",
            "model": "Dell Latitude 7440",
            "category": "computer",
            "supplier": "Dell",
            "purchase_date": "2026-01-01",
            "purchase_amount": "1500.00",
        }
        with patch(
            "app.api.v1.endpoints.assets._next_asset_code",
            return_value="AST-2026-00001",
        ):
            response = client.post("/api/v1/assets", json=payload, headers=auth_headers(manager))
        assert response.status_code == 409

    def test_returns_503_on_db_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        payload = {
            "name": "Business Laptop",
            "model": "Dell Latitude 7440",
            "category": "computer",
            "supplier": "Dell",
            "purchase_date": "2026-01-01",
            "purchase_amount": "1500.00",
        }
        with patch.object(db_session, "flush", side_effect=SQLAlchemyError("DB error")):
            response = client.post("/api/v1/assets", json=payload, headers=auth_headers(manager))
        assert response.status_code == 503


class TestGetAsset:
    def test_manager_gets_asset(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)

        response = client.get(f"/api/v1/assets/{asset.id}", headers=auth_headers(manager))

        assert response.status_code == 200
        assert response.json()["data"]["id"] == asset.id

    def test_holder_gets_only_assigned_asset(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        other_holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, responsible_person_id=holder.id)

        ok = client.get(f"/api/v1/assets/{asset.id}", headers=auth_headers(holder))
        forbidden = client.get(f"/api/v1/assets/{asset.id}", headers=auth_headers(other_holder))

        assert ok.status_code == 200
        assert forbidden.status_code == 403

    def test_returns_404_for_soft_deleted_asset(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session, deleted_at=datetime.now(UTC))

        response = client.get(f"/api/v1/assets/{asset.id}", headers=auth_headers(manager))

        assert response.status_code == 404


class TestUpdateAsset:
    def test_updates_asset_fields(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)
        current_version = asset.version

        response = client.patch(
            f"/api/v1/assets/{asset.id}",
            json={"location": "Kaohsiung Office", "version": current_version},
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["location"] == "Kaohsiung Office"
        assert data["version"] == current_version + 1

    def test_rejects_stale_version(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)

        response = client.patch(
            f"/api/v1/assets/{asset.id}",
            json={"location": "Kaohsiung Office", "version": asset.version + 1},
            headers=auth_headers(manager),
        )

        assert response.status_code == 409

    def test_rejects_status_update(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)

        response = client.patch(
            f"/api/v1/assets/{asset.id}",
            json={"status": "disposed", "version": asset.version},
            headers=auth_headers(manager),
        )

        assert response.status_code == 422

    def test_clears_optional_location_and_department(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session, location="Taipei HQ", department="IT")

        response = client.patch(
            f"/api/v1/assets/{asset.id}",
            json={"location": None, "department": None, "version": asset.version},
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["location"] == ""
        assert data["department"] == ""

    def test_returns_404_for_missing_asset(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        response = client.patch(
            "/api/v1/assets/00000000-0000-0000-0000-000000000000",
            json={"location": "Kaohsiung", "version": 1},
            headers=auth_headers(manager),
        )
        assert response.status_code == 404

    def test_rejects_warranty_expiry_before_stored_purchase_date(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)  # purchase_date = 2026-01-01

        response = client.patch(
            f"/api/v1/assets/{asset.id}",
            json={"warranty_expiry": "2025-12-31", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_returns_503_on_db_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)
        with patch.object(db_session, "commit", side_effect=SQLAlchemyError("DB error")):
            response = client.patch(
                f"/api/v1/assets/{asset.id}",
                json={"location": "Kaohsiung", "version": asset.version},
                headers=auth_headers(manager),
            )
        assert response.status_code == 503


class TestAssetCreateSchema:
    def test_empty_name_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            AssetCreate(
                name="",
                model="Dell Latitude 7440",
                category="computer",
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
                category="computer",
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
            category="computer",
            supplier="Dell",
            purchase_date=_PURCHASE_DATE,
            purchase_amount=Decimal("1500.00"),
            location="Taipei HQ",
            department="IT",
        )
        assert asset.name == "Business Laptop"
        assert asset.purchase_amount == Decimal("1500.00")

    def test_future_purchase_date_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            AssetCreate(
                name="Laptop",
                model="Dell Latitude 7440",
                category="computer",
                supplier="Dell",
                purchase_date=date(9999, 1, 1),
                purchase_amount=Decimal("1500.00"),
            )

    def test_warranty_expiry_before_purchase_date_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            AssetCreate(
                name="Laptop",
                model="Dell Latitude 7440",
                category="computer",
                supplier="Dell",
                purchase_date=_PURCHASE_DATE,
                purchase_amount=Decimal("1500.00"),
                warranty_expiry=date(2025, 12, 31),
            )


class TestAssignAsset:
    """FSM T2: in_stock -> in_use, manager-only."""

    def test_assigns_in_stock_asset_to_holder(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER, name="Alice")
        asset = _make_asset(db_session, status=AssetStatus.IN_STOCK)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={"responsible_person_id": holder.id, "version": asset.version},
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "in_use"
        assert data["responsible_person_id"] == holder.id
        assert data["responsible_person"]["id"] == holder.id
        assert data["version"] == asset.version + 1

    def test_holder_cannot_assign(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        target = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={"responsible_person_id": target.id, "version": asset.version},
            headers=auth_headers(holder),
        )
        assert response.status_code == 403

    def test_anonymous_cannot_assign(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
    ) -> None:
        target = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session)
        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={"responsible_person_id": target.id, "version": asset.version},
        )
        assert response.status_code == 401

    @pytest.mark.parametrize(
        "current_status",
        [
            AssetStatus.IN_USE,
            AssetStatus.PENDING_REPAIR,
            AssetStatus.UNDER_REPAIR,
            AssetStatus.DISPOSED,
        ],
    )
    def test_rejects_non_in_stock_status(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        current_status: AssetStatus,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        target = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=current_status)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={"responsible_person_id": target.id, "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_returns_404_for_missing_asset(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        target = make_user(role=UserRole.HOLDER)
        response = client.post(
            "/api/v1/assets/00000000-0000-0000-0000-000000000000/assign",
            json={"responsible_person_id": target.id, "version": 1},
            headers=auth_headers(manager),
        )
        assert response.status_code == 404

    def test_returns_404_for_soft_deleted_asset(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        target = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, deleted_at=datetime.now(UTC))

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={"responsible_person_id": target.id, "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 404

    def test_rejects_unknown_target_user(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={
                "responsible_person_id": "00000000-0000-0000-0000-000000000000",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_rejects_manager_role_target(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        another_manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={"responsible_person_id": another_manager.id, "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_rejects_soft_deleted_target(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        target = make_user(role=UserRole.HOLDER, deleted=True)
        asset = _make_asset(db_session)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={"responsible_person_id": target.id, "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_rejects_in_stock_asset_with_stray_responsible_person(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Defense in depth: FSM T2 requires responsible_person_id IS NULL even when status is in_stock.
        manager = make_user(role=UserRole.MANAGER)
        existing_holder = make_user(role=UserRole.HOLDER)
        target = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_STOCK,
            responsible_person_id=existing_holder.id,
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={"responsible_person_id": target.id, "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_rejects_stale_version(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        target = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={"responsible_person_id": target.id, "version": asset.version + 1},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_returns_503_on_db_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        target = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session)

        with patch.object(db_session, "commit", side_effect=SQLAlchemyError("DB error")):
            response = client.post(
                f"/api/v1/assets/{asset.id}/assign",
                json={"responsible_person_id": target.id, "version": asset.version},
                headers=auth_headers(manager),
            )
        assert response.status_code == 503


class TestUnassignAsset:
    """FSM T5: in_use -> in_stock, manager-only."""

    def test_unassigns_in_use_asset(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            responsible_person_id=holder.id,
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={"reason": "Employee transfer", "version": asset.version},
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "in_stock"
        assert data["responsible_person_id"] is None
        assert data["responsible_person"] is None
        assert data["version"] == asset.version + 1

    def test_holder_cannot_unassign(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            responsible_person_id=holder.id,
        )
        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={"reason": "transfer", "version": asset.version},
            headers=auth_headers(holder),
        )
        assert response.status_code == 403

    @pytest.mark.parametrize(
        "current_status",
        [
            AssetStatus.IN_STOCK,
            AssetStatus.PENDING_REPAIR,
            AssetStatus.UNDER_REPAIR,
            AssetStatus.DISPOSED,
        ],
    )
    def test_rejects_non_in_use_status(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        current_status: AssetStatus,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session, status=current_status)

        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={"reason": "transfer", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_returns_404_for_missing_asset(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        response = client.post(
            "/api/v1/assets/00000000-0000-0000-0000-000000000000/unassign",
            json={"reason": "transfer", "version": 1},
            headers=auth_headers(manager),
        )
        assert response.status_code == 404

    def test_returns_404_for_soft_deleted_asset(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            deleted_at=datetime.now(UTC),
        )
        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={"reason": "transfer", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 404

    def test_requires_reason(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            responsible_person_id=holder.id,
        )
        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={"reason": "", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_rejects_reason_over_500_chars(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            responsible_person_id=holder.id,
        )
        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={"reason": "x" * 501, "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_rejects_stale_version(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            responsible_person_id=holder.id,
        )
        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={"reason": "transfer", "version": asset.version + 1},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    @pytest.mark.parametrize(
        "active_status",
        [RepairRequestStatus.PENDING_REVIEW, RepairRequestStatus.UNDER_REPAIR],
    )
    def test_blocked_by_active_repair_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        active_status: RepairRequestStatus,
    ) -> None:
        # Belt-and-suspenders: even if asset.status somehow remains in_use, an active repair
        # request must block unassign per FSM T5.
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            responsible_person_id=holder.id,
        )
        _make_repair_request(
            db_session,
            asset=asset,
            requester=holder,
            status=active_status,
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={"reason": "transfer", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    @pytest.mark.parametrize(
        "inactive_status",
        [RepairRequestStatus.COMPLETED, RepairRequestStatus.REJECTED],
    )
    def test_inactive_repair_request_does_not_block(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        inactive_status: RepairRequestStatus,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            responsible_person_id=holder.id,
        )
        _make_repair_request(
            db_session,
            asset=asset,
            requester=holder,
            status=inactive_status,
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={"reason": "transfer", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 200

    def test_soft_deleted_repair_request_does_not_block(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            responsible_person_id=holder.id,
        )
        _make_repair_request(
            db_session,
            asset=asset,
            requester=holder,
            status=RepairRequestStatus.PENDING_REVIEW,
            deleted_at=datetime.now(UTC),
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={"reason": "transfer", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 200

    def test_returns_503_on_db_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            responsible_person_id=holder.id,
        )
        with patch.object(db_session, "commit", side_effect=SQLAlchemyError("DB error")):
            response = client.post(
                f"/api/v1/assets/{asset.id}/unassign",
                json={"reason": "transfer", "version": asset.version},
                headers=auth_headers(manager),
            )
        assert response.status_code == 503


class TestDisposeAsset:
    """FSM T3: in_stock -> disposed, manager-only."""

    def test_disposes_in_stock_asset(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session, status=AssetStatus.IN_STOCK)

        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={
                "disposal_reason": "End of life — exceeded warranty",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "disposed"
        assert data["disposal_reason"] == "End of life — exceeded warranty"
        assert data["version"] == asset.version + 1

    def test_holder_cannot_dispose(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session)
        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "EOL", "version": asset.version},
            headers=auth_headers(holder),
        )
        assert response.status_code == 403

    @pytest.mark.parametrize(
        "current_status",
        [
            AssetStatus.IN_USE,
            AssetStatus.PENDING_REPAIR,
            AssetStatus.UNDER_REPAIR,
            AssetStatus.DISPOSED,
        ],
    )
    def test_rejects_non_in_stock_status(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        current_status: AssetStatus,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session, status=current_status)

        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "EOL", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_rejects_in_stock_asset_with_stray_responsible_person(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_STOCK,
            responsible_person_id=holder.id,
        )
        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "EOL", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_returns_404_for_missing_asset(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        response = client.post(
            "/api/v1/assets/00000000-0000-0000-0000-000000000000/dispose",
            json={"disposal_reason": "EOL", "version": 1},
            headers=auth_headers(manager),
        )
        assert response.status_code == 404

    def test_returns_404_for_soft_deleted_asset(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session, deleted_at=datetime.now(UTC))
        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "EOL", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 404

    def test_requires_disposal_reason(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)
        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_rejects_disposal_reason_over_500_chars(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)
        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "x" * 501, "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_rejects_stale_version(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)
        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "EOL", "version": asset.version + 1},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_returns_503_on_db_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)
        with patch.object(db_session, "commit", side_effect=SQLAlchemyError("DB error")):
            response = client.post(
                f"/api/v1/assets/{asset.id}/dispose",
                json={"disposal_reason": "EOL", "version": asset.version},
                headers=auth_headers(manager),
            )
        assert response.status_code == 503
