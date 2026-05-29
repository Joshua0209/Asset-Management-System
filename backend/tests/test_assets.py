from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole
from app.schemas.asset import AssetCreate, AssetUpdate

_PURCHASE_DATE = date(2026, 1, 1)
_ASSIGNMENT_DATE_ISO = "2026-04-15"
_UNASSIGNMENT_DATE_ISO = "2026-04-20"


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


_REPAIR_ID_COUNTER = itertools.count(1)


def _unique_repair_id() -> str:
    return f"REP-2026-{next(_REPAIR_ID_COUNTER):05d}"


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
        repair_id=_unique_repair_id(),
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
        holder = make_user(
            role=UserRole.HOLDER,
            name="Alice",
            department="Engineering",
            location="Hsinchu Fab12",
        )
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
            "department": holder.department,
        }

    def test_responsible_person_exposes_holder_department(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Issue #97 / Q21: the AssetDetail UI renders the holder's
        # organisational department alongside the asset's owning
        # department. The API must surface holder.department through
        # the nested responsible_person object so the frontend can
        # distinguish the two without a second round-trip.
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(
            role=UserRole.HOLDER,
            name="Bob",
            department="研發中心",
        )
        _make_asset(
            db_session,
            asset_code="AST-2026-00009",
            responsible_person_id=holder.id,
            department="資訊維運部",
        )

        response = client.get("/api/v1/assets?sort=asset_code", headers=auth_headers(manager))

        assert response.status_code == 200
        item = response.json()["data"][0]
        assert item["department"] == "資訊維運部"
        assert item["responsible_person"]["department"] == "研發中心"

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
        response = client.get("/api/v1/assets?sort=password_hash", headers=auth_headers(manager))
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

    def test_registers_asset_defaults_missing_location_department_to_manager(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(
            role=UserRole.MANAGER,
            department="資訊維運部",
            location="Taipei Storage",
        )
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
        assert data["location"] == "Taipei Storage"
        assert data["department"] == "資訊維運部"

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


class TestAssetUpdateSchema:
    """Cover the cross-field validator on ``AssetUpdate`` (PATCH payload).

    ``TestAssetCreateSchema`` covers the same rules on ``AssetCreate``; these
    exist because the PATCH validator runs against a different field shape
    (every field is ``Optional`` with a default of ``None``) and only enforces
    the rule when the caller actually set the field. The non-null guard at
    line 82, the future-purchase-date guard at line 84, and the warranty
    ordering guard at line 90 are otherwise unreachable from existing tests.
    """

    def test_explicit_null_for_non_nullable_field_raises(self) -> None:
        # Caller cannot wipe a required field by sending ``null`` in PATCH.
        with pytest.raises(ValidationError, match="name cannot be null"):
            AssetUpdate.model_validate({"name": None, "version": 1})

    def test_explicit_null_for_purchase_amount_raises(self) -> None:
        with pytest.raises(ValidationError, match="purchase_amount cannot be null"):
            AssetUpdate.model_validate({"purchase_amount": None, "version": 1})

    def test_future_purchase_date_raises(self) -> None:
        with pytest.raises(ValidationError, match="purchase_date must not be in the future"):
            AssetUpdate.model_validate({"purchase_date": "9999-01-01", "version": 1})

    def test_warranty_expiry_equal_to_purchase_date_raises(self) -> None:
        # Validator says "must be after", so equal also fails. Both dates must
        # be in the past — otherwise the future-purchase-date guard would fire
        # first and this test would pass for the wrong reason once the system
        # clock crosses the chosen date.
        with pytest.raises(ValidationError, match="warranty_expiry must be after purchase_date"):
            AssetUpdate.model_validate(
                {
                    "purchase_date": "2025-06-01",
                    "warranty_expiry": "2025-06-01",
                    "version": 1,
                }
            )

    def test_warranty_expiry_before_purchase_date_raises(self) -> None:
        # Both dates must be in the past, otherwise the future-purchase-date
        # guard fires first and the test would pass for the wrong reason.
        with pytest.raises(ValidationError, match="warranty_expiry must be after purchase_date"):
            AssetUpdate.model_validate(
                {
                    "purchase_date": "2025-06-01",
                    "warranty_expiry": "2025-01-01",
                    "version": 1,
                }
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
        current_version = asset.version

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={
                "responsible_person_id": holder.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "version": current_version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "in_use"
        assert data["responsible_person_id"] == holder.id
        assert data["responsible_person"]["id"] == holder.id
        assert data["department"] == "Engineering"
        assert data["location"] == "Hsinchu Fab12"
        assert data["version"] == current_version + 1

    def test_assign_syncs_department_and_location_from_holder(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(
            role=UserRole.HOLDER,
            department="研發中心",
            location="Hsinchu Fab12",
        )
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_STOCK,
            department="資訊維運部",
            location="Taipei HQ",
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={
                "responsible_person_id": holder.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        assert response.json()["data"]["department"] == "研發中心"
        assert response.json()["data"]["location"] == "Hsinchu Fab12"

    def test_assign_rejects_client_supplied_location(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_STOCK)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={
                "responsible_person_id": holder.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Hsinchu Fab12",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 422

    def test_assign_rejects_client_supplied_department(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_STOCK)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={
                "responsible_person_id": holder.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "department": "研發中心",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 422

    def test_assign_syncs_holder_department(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(
            role=UserRole.HOLDER,
            department="研發中心",
            location="Hsinchu Fab12",
        )
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_STOCK,
            department="資訊維運部",
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={
                "responsible_person_id": holder.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["department"] == "研發中心"
        assert data["location"] == "Hsinchu Fab12"
        assert data["responsible_person"]["department"] == "研發中心"

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
            json={
                "responsible_person_id": target.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset.version,
            },
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
            json={
                "responsible_person_id": target.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset.version,
            },
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
        manager = make_user(
            role=UserRole.MANAGER,
            department="資訊維運部",
            location="Taipei Storage",
        )
        target = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=current_status)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={
                "responsible_person_id": target.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset.version,
            },
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
            json={
                "responsible_person_id": target.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": 1,
            },
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
            json={
                "responsible_person_id": target.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset.version,
            },
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
            json={
                "responsible_person_id": another_manager.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset.version,
            },
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
            json={
                "responsible_person_id": target.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset.version,
            },
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
        # FSM T2 requires responsible_person_id IS NULL even when status is in_stock.
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
            json={
                "responsible_person_id": target.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset.version,
            },
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
            json={
                "responsible_person_id": target.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset.version + 1,
            },
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
                json={
                    "responsible_person_id": target.id,
                    "assignment_date": _ASSIGNMENT_DATE_ISO,
                    "location": "Taipei HQ",
                    "version": asset.version,
                },
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
        current_version = asset.version

        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={
                "reason": "Employee transfer",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "version": current_version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "in_stock"
        assert data["responsible_person_id"] is None
        assert data["responsible_person"] is None
        assert data["department"] == "資訊維運部"
        assert data["location"] == "Taipei Storage"
        assert data["version"] == current_version + 1

    def test_unassign_syncs_department_and_location_from_manager(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(
            role=UserRole.MANAGER,
            department="資訊維運部",
            location="Taipei Storage",
        )
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            responsible_person_id=holder.id,
            department="研發中心",
            location="Hsinchu Fab12",
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={
                "reason": "Returned to storage",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        assert response.json()["data"]["department"] == "資訊維運部"
        assert response.json()["data"]["location"] == "Taipei Storage"

    def test_unassign_rejects_client_supplied_location(
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
            json={
                "reason": "Returned to storage",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 422

    def test_unassign_rejects_client_supplied_department(
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
            json={
                "reason": "Returned to storage",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "department": "資訊維運部",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 422

    def test_unassign_syncs_manager_department(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(
            role=UserRole.MANAGER,
            department="資訊維運部",
            location="Taipei Storage",
        )
        holder = make_user(role=UserRole.HOLDER, department="研發中心")
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            responsible_person_id=holder.id,
            department="資訊維運部",
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={
                "reason": "Returned to storage",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["department"] == "資訊維運部"
        assert data["location"] == "Taipei Storage"
        assert data["responsible_person"] is None

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
            json={
                "reason": "transfer",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version,
            },
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
            json={
                "reason": "transfer",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version,
            },
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
            json={
                "reason": "transfer",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": 1,
            },
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
            json={
                "reason": "transfer",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version,
            },
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
            json={
                "reason": "",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version,
            },
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
            json={
                "reason": "x" * 501,
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version,
            },
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
            json={
                "reason": "transfer",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version + 1,
            },
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
            json={
                "reason": "transfer",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version,
            },
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
            json={
                "reason": "transfer",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version,
            },
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
            json={
                "reason": "transfer",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version,
            },
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
                json={
                    "reason": "transfer",
                    "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                    "location": "Taipei Storage",
                    "version": asset.version,
                },
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
        current_version = asset.version

        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={
                "disposal_reason": "End of life — exceeded warranty",
                "version": current_version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "disposed"
        assert data["disposal_reason"] == "End of life — exceeded warranty"
        assert data["version"] == current_version + 1

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
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_STOCK)
        _make_repair_request(
            db_session,
            asset=asset,
            requester=holder,
            status=active_status,
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "EOL", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409
        assert response.json()["error"]["message"] == (
            "Cannot dispose asset with an active repair request."
        )

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
        asset = _make_asset(db_session, status=AssetStatus.IN_STOCK)
        _make_repair_request(
            db_session,
            asset=asset,
            requester=holder,
            status=inactive_status,
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "EOL", "version": asset.version},
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
        asset = _make_asset(db_session, status=AssetStatus.IN_STOCK)
        _make_repair_request(
            db_session,
            asset=asset,
            requester=holder,
            status=RepairRequestStatus.PENDING_REVIEW,
            deleted_at=datetime.now(UTC),
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "EOL", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 200

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


class TestAssetTransition409ErrorCodes:
    """Pin the granular `error.code` values for 409s on FSM transitions.

    `docs/system-design/12-api-design.md` distinguishes:
      - `invalid_transition` — FSM precondition violated
      - `conflict`           — optimistic-lock version mismatch
    A regression that collapses these back to a single `"conflict"` code would
    break clients that branch on `error.code`.
    """

    def test_assign_returns_invalid_transition_when_asset_not_in_stock(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        target = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_USE, responsible_person_id=target.id)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={
                "responsible_person_id": target.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_transition"

    def test_assign_returns_invalid_transition_when_in_stock_asset_already_assigned(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # FSM T2 desync guard: status=in_stock but responsible_person_id is set.
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
            json={
                "responsible_person_id": target.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_transition"

    def test_assign_returns_conflict_on_stale_version(
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
            json={
                "responsible_person_id": target.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset.version + 1,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_unassign_returns_invalid_transition_when_asset_not_in_use(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session, status=AssetStatus.IN_STOCK)

        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={
                "reason": "transfer",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_transition"

    def test_unassign_returns_invalid_transition_when_blocked_by_active_repair(
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
            status=RepairRequestStatus.UNDER_REPAIR,
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={
                "reason": "transfer",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        body = response.json()["error"]
        assert body["code"] == "invalid_transition"
        assert body["message"] == "Cannot unassign asset with an active repair request."

    def test_unassign_returns_conflict_on_stale_version(
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
            json={
                "reason": "transfer",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version + 1,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_dispose_returns_invalid_transition_when_asset_not_in_stock(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session, status=AssetStatus.IN_USE)

        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "EOL", "version": asset.version},
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_transition"

    def test_dispose_returns_invalid_transition_when_in_stock_asset_still_assigned(
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
        assert response.json()["error"]["code"] == "invalid_transition"

    def test_dispose_returns_invalid_transition_when_blocked_by_active_repair(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_STOCK)
        _make_repair_request(
            db_session,
            asset=asset,
            requester=holder,
            status=RepairRequestStatus.PENDING_REVIEW,
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "EOL", "version": asset.version},
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_transition"

    def test_dispose_returns_conflict_on_stale_version(
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
        assert response.json()["error"]["code"] == "conflict"

    def test_update_returns_conflict_on_stale_version(
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
            json={"location": "New Location", "version": asset.version + 1},
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"


class TestAssignmentDateFields:
    """Issue #31: assign/unassign now persist explicit dates supplied by the manager."""

    def test_assign_persists_assignment_date_and_clears_unassignment_date(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_STOCK)
        # Simulate the asset having a stale unassignment_date from a prior cycle
        # so we can assert the assign endpoint resets the pair.
        asset.unassignment_date = date(2026, 3, 1)
        db_session.commit()

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={
                "responsible_person_id": holder.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["assignment_date"] == _ASSIGNMENT_DATE_ISO
        assert body["unassignment_date"] is None

    def test_assign_rejects_future_assignment_date(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_STOCK)
        future = (datetime.now(UTC).date()).replace(year=datetime.now(UTC).year + 1)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={
                "responsible_person_id": holder.id,
                "assignment_date": future.isoformat(),
                "location": "Taipei HQ",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 422

    def test_assign_requires_assignment_date(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_STOCK)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            # Deliberately omits assignment_date.
            json={"responsible_person_id": holder.id, "version": asset.version},
            headers=auth_headers(manager),
        )

        assert response.status_code == 422

    def test_unassign_persists_unassignment_date_and_preserves_assignment_date(
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
        asset.assignment_date = date(2026, 4, 1)
        db_session.commit()

        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={
                "reason": "Employee transfer",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "location": "Taipei Storage",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["unassignment_date"] == _UNASSIGNMENT_DATE_ISO
        # Spec: assignment_date is preserved on unassign so the pair captures
        # the most recent assignment window.
        assert body["assignment_date"] == "2026-04-01"

    def test_unassign_rejects_future_unassignment_date(
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
        future = datetime.now(UTC).date().replace(year=datetime.now(UTC).year + 1)

        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={
                "reason": "transfer",
                "unassignment_date": future.isoformat(),
                "location": "Taipei Storage",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 422

    def test_unassign_rejects_unassignment_date_before_assignment_date(
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
        asset.assignment_date = date(2026, 4, 20)
        db_session.commit()

        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={
                "reason": "transfer",
                # One day earlier than assignment_date.
                "unassignment_date": "2026-04-19",
                "location": "Taipei Storage",
                "version": asset.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_unassignment_date"


class TestListAssetsFilterBranches:
    """Exercise the status / department / location filter branches of
    ``_build_asset_filters``. Existing tests only set ``category``; without
    these the three sibling branches stay unmeasured."""

    @pytest.mark.parametrize(
        ("kept_kwargs", "other_kwargs", "query"),
        [
            pytest.param(
                {"status": AssetStatus.IN_STOCK},
                {"status": AssetStatus.DISPOSED},
                "status=in_stock",
                id="status",
            ),
            pytest.param(
                {"department": "HR"},
                {"department": "IT"},
                "department=HR",
                id="department",
            ),
            pytest.param(
                {"location": "Kaohsiung Office"},
                {"location": "Taipei HQ"},
                "location=Kaohsiung+Office",
                id="location",
            ),
        ],
    )
    def test_filter_returns_only_matching_assets(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        kept_kwargs: dict[str, Any],
        other_kwargs: dict[str, Any],
        query: str,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        _make_asset(db_session, asset_code="AST-2026-00001", **kept_kwargs)
        _make_asset(db_session, asset_code="AST-2026-00002", **other_kwargs)

        response = client.get(f"/api/v1/assets?{query}", headers=auth_headers(manager))

        assert response.status_code == 200
        codes = [item["asset_code"] for item in response.json()["data"]]
        assert codes == ["AST-2026-00001"]


class TestGetAssetDbError:
    def test_returns_503_on_sqlalchemy_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        scalar_skip_auth: Callable[[BaseException], Callable[..., Any]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)

        # Both ``get_current_user`` and ``get_asset`` use ``db.scalar``; the
        # auth lookup is always the first call. ``scalar_skip_auth`` passes
        # it through and raises on every subsequent call so we exercise the
        # SQLAlchemyError branch (line 380-385) rather than the 401 path.
        with patch.object(
            db_session, "scalar", side_effect=scalar_skip_auth(SQLAlchemyError("DB down"))
        ):
            response = client.get(f"/api/v1/assets/{asset.id}", headers=auth_headers(manager))

        assert response.status_code == 503


class TestListMyAssetsDbError:
    def test_returns_503_on_sqlalchemy_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)

        with patch.object(db_session, "scalars", side_effect=SQLAlchemyError("DB down")):
            response = client.get("/api/v1/assets/mine", headers=auth_headers(holder))

        assert response.status_code == 503


class TestAssetCodeSequenceCorruption:
    """Guard against silent recovery from a malformed ``asset_code`` row.

    If we ever wrote a code that doesn't end in a parseable integer (legacy
    import, schema migration bug, manual SQL touch), ``_next_asset_code``
    would re-collide on every retry. The endpoint must fail loud with 500.
    """

    def test_returns_500_when_existing_asset_code_has_non_numeric_suffix(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        # Matches the AST-2026- LIKE filter so it lands as the "latest_code",
        # but the suffix is not int-parseable.
        _make_asset(db_session, asset_code="AST-2026-BADCODE")

        response = client.post(
            "/api/v1/assets",
            json={
                "name": "Business Laptop",
                "model": "Dell Latitude 7440",
                "category": "computer",
                "supplier": "Dell",
                "purchase_date": "2026-01-01",
                "purchase_amount": "1500.00",
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 500
        body = response.json()["error"]
        assert body["code"] == "internal_server_error"
        assert "corrupted" in body["message"]


class TestRegisterAssetIntegrityErrors:
    """Distinguish ``asset_code`` uniqueness collisions (retryable, 409) from
    other constraint violations (programmer/data error, 422)."""

    def test_non_asset_code_integrity_error_returns_422(
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

        # Trip the registration retry loop's IntegrityError handler with an
        # ``orig`` message that does NOT contain ``asset_code``: the endpoint
        # must surface this as a validation error, not retry the loop forever.
        with patch.object(
            db_session,
            "flush",
            side_effect=IntegrityError(
                "INSERT INTO assets ...",
                {},
                Exception("CHECK constraint failed on purchase_amount"),
            ),
        ):
            response = client.post("/api/v1/assets", json=payload, headers=auth_headers(manager))

        assert response.status_code == 422
        body = response.json()["error"]
        assert body["code"] == "validation_error"
        assert "violates database constraints" in body["message"]


_STALE_DATA_CASE = pytest.param(
    StaleDataError("row was modified"),
    409,
    "conflict",
    "modified by another user",
    id="stale-data-409",
)
_INTEGRITY_CASE = pytest.param(
    IntegrityError("UPDATE assets ...", {}, Exception("constraint violated")),
    422,
    "validation_error",
    "violates database constraints",
    id="integrity-422",
)
_COMMIT_ERROR_CASES = [_STALE_DATA_CASE, _INTEGRITY_CASE]


class TestAssetMutationCommitErrors:
    """``StaleDataError`` → 409 and ``IntegrityError`` → 422 on the four
    mutation endpoints (update / assign / unassign / dispose).

    The catch-all ``SQLAlchemyError`` → 503 branch is already covered by each
    endpoint's ``test_returns_503_on_db_error``; these cover the two typed
    branches that sit above it. ``StaleDataError`` in particular is the
    optimistic-locking signal that the frontend conflict UI consumes.
    """

    @pytest.mark.parametrize(
        ("commit_error", "expected_status", "expected_code", "message_substring"),
        _COMMIT_ERROR_CASES,
    )
    def test_update_commit_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        commit_error: SQLAlchemyError,
        expected_status: int,
        expected_code: str,
        message_substring: str,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)

        with patch.object(db_session, "commit", side_effect=commit_error):
            response = client.patch(
                f"/api/v1/assets/{asset.id}",
                json={"location": "Kaohsiung", "version": asset.version},
                headers=auth_headers(manager),
            )

        assert response.status_code == expected_status
        body = response.json()["error"]
        assert body["code"] == expected_code
        assert message_substring in body["message"]

    @pytest.mark.parametrize(
        ("commit_error", "expected_status", "expected_code", "message_substring"),
        _COMMIT_ERROR_CASES,
    )
    def test_assign_commit_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        commit_error: SQLAlchemyError,
        expected_status: int,
        expected_code: str,
        message_substring: str,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        target = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session)

        with patch.object(db_session, "commit", side_effect=commit_error):
            response = client.post(
                f"/api/v1/assets/{asset.id}/assign",
                json={
                    "responsible_person_id": target.id,
                    "assignment_date": _ASSIGNMENT_DATE_ISO,
                    "location": "Taipei HQ",
                    "version": asset.version,
                },
                headers=auth_headers(manager),
            )

        assert response.status_code == expected_status
        body = response.json()["error"]
        assert body["code"] == expected_code
        assert message_substring in body["message"]

    @pytest.mark.parametrize(
        ("commit_error", "expected_status", "expected_code", "message_substring"),
        _COMMIT_ERROR_CASES,
    )
    def test_unassign_commit_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        commit_error: SQLAlchemyError,
        expected_status: int,
        expected_code: str,
        message_substring: str,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            responsible_person_id=holder.id,
        )

        with patch.object(db_session, "commit", side_effect=commit_error):
            response = client.post(
                f"/api/v1/assets/{asset.id}/unassign",
                json={
                    "reason": "transfer",
                    "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                    "location": "Taipei Storage",
                    "version": asset.version,
                },
                headers=auth_headers(manager),
            )

        assert response.status_code == expected_status
        body = response.json()["error"]
        assert body["code"] == expected_code
        assert message_substring in body["message"]

    @pytest.mark.parametrize(
        ("commit_error", "expected_status", "expected_code", "message_substring"),
        _COMMIT_ERROR_CASES,
    )
    def test_dispose_commit_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        commit_error: SQLAlchemyError,
        expected_status: int,
        expected_code: str,
        message_substring: str,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session, status=AssetStatus.IN_STOCK)

        with patch.object(db_session, "commit", side_effect=commit_error):
            response = client.post(
                f"/api/v1/assets/{asset.id}/dispose",
                json={"disposal_reason": "EOL", "version": asset.version},
                headers=auth_headers(manager),
            )

        assert response.status_code == expected_status
        body = response.json()["error"]
        assert body["code"] == expected_code
        assert message_substring in body["message"]
