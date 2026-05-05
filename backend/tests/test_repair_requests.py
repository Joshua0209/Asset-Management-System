from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.main import app
from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole
from app.services.image_storage import ImageStorageError, get_image_storage

_PURCHASE_DATE = date(2026, 1, 1)
_REPAIR_DATE = date(2026, 4, 20)
_PNG_BYTES = b"\x89PNG\r\n\x1a\nvalid-png-payload"
_JPEG_BYTES = b"\xff\xd8valid-jpeg-payload\xff\xd9"


_COMPLETE_PAYLOAD: dict[str, Any] = {
    "repair_date": _REPAIR_DATE.isoformat(),
    "fault_content": "GPU connector loose.",
    "repair_plan": "Replaced GPU ribbon cable.",
    "repair_cost": "3500.00",
    "repair_vendor": "Apple Authorized Service",
}


def _details_payload(version: int) -> dict[str, Any]:
    return {"fault_content": "Updated content.", "version": version}


def _complete_payload(version: int) -> dict[str, Any]:
    return {**_COMPLETE_PAYLOAD, "version": version}


class FailingImageStorage:
    def save(
        self,
        *,
        repair_request_id: str,
        image_id: str,
        suffix: str,
        content: bytes,
    ) -> str:
        raise ImageStorageError("storage backend unavailable")

    def open(self, storage_key: str) -> tuple[bytes, str]:
        raise ImageStorageError("storage backend unavailable")

    def cleanup(self, storage_keys: list[str]) -> None:
        return None


def _make_asset(
    session: Session,
    holder: User | None = None,
    *,
    asset_code: str = "AST-2026-00001",
    status: AssetStatus | None = None,
) -> Asset:
    asset_status = (
        status if status is not None else AssetStatus.IN_USE if holder else AssetStatus.IN_STOCK
    )
    asset = Asset(
        asset_code=asset_code,
        name="Business Laptop",
        model="Dell Latitude 7440",
        category="computer",
        supplier="Dell",
        purchase_date=_PURCHASE_DATE,
        purchase_amount=Decimal("1500.00"),
        location="Taipei HQ",
        department="IT",
        status=asset_status,
        responsible_person_id=holder.id if holder else None,
    )
    session.add(asset)
    session.flush()
    return asset


def _make_repair_request(
    session: Session,
    asset: Asset,
    requester: User,
    *,
    status: RepairRequestStatus = RepairRequestStatus.PENDING_REVIEW,
    reviewer: User | None = None,
    fault_description: str = "Screen flickers.",
) -> RepairRequest:
    repair_request = RepairRequest(
        asset_id=asset.id,
        requester_id=requester.id,
        reviewer_id=reviewer.id if reviewer else None,
        status=status,
        fault_description=fault_description,
    )
    session.add(repair_request)
    session.flush()
    return repair_request


class TestListRepairRequests:
    def test_empty_database_returns_empty_list(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        response = client.get("/api/v1/repair-requests", headers=auth_headers(manager))
        assert response.status_code == 200
        assert response.json() == {
            "data": [],
            "meta": {"total": 0, "page": 1, "per_page": 20, "total_pages": 0},
        }

    def test_returns_repair_requests_with_images_field(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER, name="Holder")
        asset = _make_asset(db_session, holder)
        rr = RepairRequest(
            asset_id=asset.id,
            requester_id=holder.id,
            status=RepairRequestStatus.PENDING_REVIEW,
            fault_description="Screen flickers.",
        )
        db_session.add(rr)
        db_session.commit()

        response = client.get("/api/v1/repair-requests", headers=auth_headers(holder))
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert "images" in data[0]
        assert data[0]["images"] == []
        assert data[0]["asset"] == {
            "id": asset.id,
            "asset_code": "AST-2026-00001",
            "name": "Business Laptop",
        }
        assert data[0]["requester"] == {"id": holder.id, "name": "Holder"}

    def test_excludes_soft_deleted_repair_requests(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
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

        response = client.get("/api/v1/repair-requests", headers=auth_headers(holder))
        assert response.json()["data"] == []

    def test_returns_503_on_db_error(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        with patch.object(db_session, "scalars", side_effect=SQLAlchemyError("DB error")):
            response = client.get("/api/v1/repair-requests", headers=auth_headers(manager))
        assert response.status_code == 503

    def test_results_ordered_newest_first(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
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
            rr.created_at = now - timedelta(hours=i)
        db_session.commit()

        response = client.get("/api/v1/repair-requests", headers=auth_headers(holder))
        timestamps = [item["created_at"] for item in response.json()["data"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_paginates_and_filters_repair_requests(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        matching_asset = _make_asset(db_session, holder, asset_code="AST-2026-00001")
        other_asset = _make_asset(db_session, holder, asset_code="AST-2026-00002")
        db_session.add_all(
            [
                RepairRequest(
                    asset_id=matching_asset.id,
                    requester_id=holder.id,
                    status=RepairRequestStatus.PENDING_REVIEW,
                    fault_description="Matching issue.",
                ),
                RepairRequest(
                    asset_id=other_asset.id,
                    requester_id=holder.id,
                    status=RepairRequestStatus.UNDER_REPAIR,
                    fault_description="Other issue.",
                ),
            ]
        )
        db_session.commit()

        response = client.get(
            f"/api/v1/repair-requests?status=pending_review&asset_id={matching_asset.id}",
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["asset"]["id"] == matching_asset.id

    def test_holder_cannot_filter_to_another_requester(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        other_holder = make_user(role=UserRole.HOLDER)

        response = client.get(
            f"/api/v1/repair-requests?requester_id={other_holder.id}",
            headers=auth_headers(holder),
        )

        assert response.status_code == 403

    def test_manager_filters_by_requester_id(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder_a = make_user(role=UserRole.HOLDER)
        holder_b = make_user(role=UserRole.HOLDER)
        asset_a = _make_asset(db_session, holder_a, asset_code="AST-2026-00001")
        asset_b = _make_asset(db_session, holder_b, asset_code="AST-2026-00002")
        db_session.add_all(
            [
                RepairRequest(
                    asset_id=asset_a.id,
                    requester_id=holder_a.id,
                    status=RepairRequestStatus.PENDING_REVIEW,
                    fault_description="A fault.",
                ),
                RepairRequest(
                    asset_id=asset_b.id,
                    requester_id=holder_b.id,
                    status=RepairRequestStatus.PENDING_REVIEW,
                    fault_description="B fault.",
                ),
            ]
        )
        db_session.commit()

        response = client.get(
            f"/api/v1/repair-requests?requester_id={holder_a.id}",
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["requester"]["id"] == holder_a.id

    def test_unsupported_sort_field_returns_422(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        response = client.get(
            "/api/v1/repair-requests?sort=fault_description",
            headers=auth_headers(manager),
        )
        assert response.status_code == 422


class TestGetRepairRequest:
    def test_manager_can_get_any_repair_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)
        repair_request = _make_repair_request(db_session, asset, holder)
        db_session.commit()

        response = client.get(
            f"/api/v1/repair-requests/{repair_request.id}",
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        assert response.json()["data"]["id"] == repair_request.id

    def test_holder_cannot_get_another_users_repair_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        other_holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)
        repair_request = _make_repair_request(db_session, asset, holder)
        db_session.commit()

        response = client.get(
            f"/api/v1/repair-requests/{repair_request.id}",
            headers=auth_headers(other_holder),
        )

        assert response.status_code == 403

    def test_malformed_request_id_is_rejected_before_database_logging(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        malicious_id = "repair-1%0Aforged-log-entry"

        with (
            patch(
                "app.api.v1.endpoints.repair_requests._get_repair_request",
                side_effect=SQLAlchemyError("database unavailable"),
            ),
            caplog.at_level(
                logging.ERROR,
                logger="app.api.v1.endpoints.repair_requests",
            ),
        ):
            response = client.get(
                f"/api/v1/repair-requests/{malicious_id}",
                headers=auth_headers(manager),
            )

        assert response.status_code == 422
        assert "repair-1" not in caplog.text
        assert "forged-log-entry" not in caplog.text


class TestRepairWorkflow:
    def test_approve_moves_request_and_asset_to_under_repair(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER, name="Manager")
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder, status=AssetStatus.PENDING_REPAIR)
        repair_request = _make_repair_request(db_session, asset, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{repair_request.id}/approve",
            json={"version": repair_request.version},
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "under_repair"
        assert data["reviewer"] == {"id": manager.id, "name": "Manager"}
        db_session.refresh(asset)
        db_session.refresh(repair_request)
        assert asset.status == AssetStatus.UNDER_REPAIR
        assert repair_request.status == RepairRequestStatus.UNDER_REPAIR
        assert repair_request.reviewer_id == manager.id

    def test_reject_moves_request_to_rejected_and_asset_to_in_use(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder, status=AssetStatus.PENDING_REPAIR)
        repair_request = _make_repair_request(db_session, asset, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{repair_request.id}/reject",
            json={
                "rejection_reason": "Issue could not be reproduced.",
                "version": repair_request.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "rejected"
        assert data["rejection_reason"] == "Issue could not be reproduced."
        db_session.refresh(asset)
        db_session.refresh(repair_request)
        assert asset.status == AssetStatus.IN_USE
        assert repair_request.status == RepairRequestStatus.REJECTED

    def test_repair_details_updates_metadata_without_changing_status(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder, status=AssetStatus.UNDER_REPAIR)
        repair_request = _make_repair_request(
            db_session,
            asset,
            holder,
            status=RepairRequestStatus.UNDER_REPAIR,
            reviewer=manager,
        )
        db_session.commit()

        response = client.patch(
            f"/api/v1/repair-requests/{repair_request.id}/repair-details",
            json={
                "repair_date": _REPAIR_DATE.isoformat(),
                "fault_content": "GPU connector loose.",
                "repair_plan": "Replace GPU ribbon cable.",
                "repair_cost": "3500.00",
                "repair_vendor": "Apple Authorized Service",
                "version": repair_request.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "under_repair"
        assert data["repair_cost"] == "3500.00"
        db_session.refresh(asset)
        db_session.refresh(repair_request)
        assert asset.status == AssetStatus.UNDER_REPAIR
        assert repair_request.status == RepairRequestStatus.UNDER_REPAIR

    def test_complete_moves_request_to_completed_and_asset_to_in_use(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder, status=AssetStatus.UNDER_REPAIR)
        repair_request = _make_repair_request(
            db_session,
            asset,
            holder,
            status=RepairRequestStatus.UNDER_REPAIR,
            reviewer=manager,
        )
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{repair_request.id}/complete",
            json={
                "repair_date": _REPAIR_DATE.isoformat(),
                "fault_content": "GPU connector loose.",
                "repair_plan": "Replaced GPU ribbon cable.",
                "repair_cost": "3500.00",
                "repair_vendor": "Apple Authorized Service",
                "version": repair_request.version,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "completed"
        assert data["completed_at"] is not None
        db_session.refresh(asset)
        db_session.refresh(repair_request)
        assert asset.status == AssetStatus.IN_USE
        assert repair_request.status == RepairRequestStatus.COMPLETED
        assert asset.responsible_person_id == holder.id

    def test_reject_requires_asset_to_still_be_pending_repair(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder, status=AssetStatus.IN_USE)
        repair_request = _make_repair_request(db_session, asset, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{repair_request.id}/reject",
            json={"rejection_reason": "No issue found.", "version": repair_request.version},
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        db_session.refresh(asset)
        db_session.refresh(repair_request)
        assert asset.status == AssetStatus.IN_USE
        assert repair_request.status == RepairRequestStatus.PENDING_REVIEW

    def test_complete_rejects_stale_request_version(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder, status=AssetStatus.UNDER_REPAIR)
        repair_request = _make_repair_request(
            db_session,
            asset,
            holder,
            status=RepairRequestStatus.UNDER_REPAIR,
        )
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{repair_request.id}/complete",
            json={
                "repair_date": _REPAIR_DATE.isoformat(),
                "fault_content": "GPU connector loose.",
                "repair_plan": "Replaced GPU ribbon cable.",
                "repair_cost": "3500.00",
                "repair_vendor": "Apple Authorized Service",
                "version": repair_request.version + 1,
            },
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        db_session.refresh(asset)
        db_session.refresh(repair_request)
        assert asset.status == AssetStatus.UNDER_REPAIR
        assert repair_request.status == RepairRequestStatus.UNDER_REPAIR

    def test_holder_cannot_approve_repair_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder, status=AssetStatus.PENDING_REPAIR)
        repair_request = _make_repair_request(db_session, asset, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{repair_request.id}/approve",
            json={"version": repair_request.version},
            headers=auth_headers(holder),
        )

        assert response.status_code == 403


def _seed_under_repair(
    db_session: Session,
    holder: User,
    reviewer: User | None = None,
) -> tuple[Asset, RepairRequest]:
    asset = _make_asset(db_session, holder, status=AssetStatus.UNDER_REPAIR)
    repair_request = _make_repair_request(
        db_session,
        asset,
        holder,
        status=RepairRequestStatus.UNDER_REPAIR,
        reviewer=reviewer,
    )
    return asset, repair_request


def _seed_pending_review(
    db_session: Session,
    holder: User,
    *,
    asset_status: AssetStatus = AssetStatus.PENDING_REPAIR,
) -> tuple[Asset, RepairRequest]:
    asset = _make_asset(db_session, holder, status=asset_status)
    repair_request = _make_repair_request(db_session, asset, holder)
    return asset, repair_request


class TestRepairWorkflowRBAC:
    """RBAC parity for the four manager-only workflow endpoints."""

    def test_holder_cannot_reject_repair_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_pending_review(db_session, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/reject",
            json={"rejection_reason": "x", "version": rr.version},
            headers=auth_headers(holder),
        )
        assert response.status_code == 403

    def test_holder_cannot_update_repair_details(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_under_repair(db_session, holder)
        db_session.commit()

        response = client.patch(
            f"/api/v1/repair-requests/{rr.id}/repair-details",
            json=_details_payload(rr.version),
            headers=auth_headers(holder),
        )
        assert response.status_code == 403

    def test_holder_cannot_complete_repair_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_under_repair(db_session, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/complete",
            json=_complete_payload(rr.version),
            headers=auth_headers(holder),
        )
        assert response.status_code == 403


class TestRepairWorkflowSoftDelete:
    """Soft-deleted requests must surface as 404 on every endpoint."""

    def test_get_returns_404_for_soft_deleted_repair_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_pending_review(db_session, holder)
        rr.deleted_at = datetime.now(UTC)
        db_session.commit()

        response = client.get(
            f"/api/v1/repair-requests/{rr.id}",
            headers=auth_headers(manager),
        )
        assert response.status_code == 404

    def test_approve_returns_404_for_soft_deleted_repair_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_pending_review(db_session, holder)
        rr.deleted_at = datetime.now(UTC)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/approve",
            json={"version": rr.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 404

    def test_reject_returns_404_for_soft_deleted_repair_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_pending_review(db_session, holder)
        rr.deleted_at = datetime.now(UTC)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/reject",
            json={"rejection_reason": "x", "version": rr.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 404

    def test_repair_details_returns_404_for_soft_deleted_repair_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_under_repair(db_session, holder)
        rr.deleted_at = datetime.now(UTC)
        db_session.commit()

        response = client.patch(
            f"/api/v1/repair-requests/{rr.id}/repair-details",
            json=_details_payload(rr.version),
            headers=auth_headers(manager),
        )
        assert response.status_code == 404

    def test_complete_returns_404_for_soft_deleted_repair_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_under_repair(db_session, holder)
        rr.deleted_at = datetime.now(UTC)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/complete",
            json=_complete_payload(rr.version),
            headers=auth_headers(manager),
        )
        assert response.status_code == 404


class TestRepairWorkflowStaleVersion:
    """Optimistic-lock parity across approve/reject/repair-details."""

    def test_approve_rejects_stale_request_version(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_pending_review(db_session, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/approve",
            json={"version": rr.version + 1},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_reject_rejects_stale_request_version(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_pending_review(db_session, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/reject",
            json={"rejection_reason": "x", "version": rr.version + 1},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_repair_details_rejects_stale_request_version(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_under_repair(db_session, holder)
        db_session.commit()

        response = client.patch(
            f"/api/v1/repair-requests/{rr.id}/repair-details",
            json=_details_payload(rr.version + 1),
            headers=auth_headers(manager),
        )
        assert response.status_code == 409


class TestRepairWorkflowFSMGuards:
    """Negative-path coverage for request-status and asset-status preconditions."""

    def test_approve_rejects_request_already_under_repair(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_under_repair(db_session, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/approve",
            json={"version": rr.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_approve_rejects_asset_in_use(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        # Desync: request stuck in pending_review, asset somehow back to in_use.
        _, rr = _seed_pending_review(
            db_session, holder, asset_status=AssetStatus.IN_USE
        )
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/approve",
            json={"version": rr.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_complete_rejects_request_in_pending_review(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_pending_review(db_session, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/complete",
            json=_complete_payload(rr.version),
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_complete_rejects_when_asset_is_in_stock(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder, status=AssetStatus.IN_STOCK)
        rr = _make_repair_request(
            db_session,
            asset,
            holder,
            status=RepairRequestStatus.UNDER_REPAIR,
        )
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/complete",
            json=_complete_payload(rr.version),
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_repair_details_rejects_request_in_pending_review(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_pending_review(db_session, holder)
        db_session.commit()

        response = client.patch(
            f"/api/v1/repair-requests/{rr.id}/repair-details",
            json=_details_payload(rr.version),
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_repair_details_rejects_when_asset_not_under_repair(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        # Desync: request still under_repair, asset already in_use.
        asset = _make_asset(db_session, holder, status=AssetStatus.IN_USE)
        rr = _make_repair_request(
            db_session,
            asset,
            holder,
            status=RepairRequestStatus.UNDER_REPAIR,
        )
        db_session.commit()

        response = client.patch(
            f"/api/v1/repair-requests/{rr.id}/repair-details",
            json=_details_payload(rr.version),
            headers=auth_headers(manager),
        )
        assert response.status_code == 409

    def test_approve_returns_409_when_asset_is_soft_deleted(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset, rr = _seed_pending_review(db_session, holder)
        asset.deleted_at = datetime.now(UTC)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/approve",
            json={"version": rr.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 409


class TestRepairWorkflowValidation:
    """Schema-level validation guarantees that the FSM contract relies on."""

    def test_repair_details_rejects_empty_payload(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_under_repair(db_session, holder)
        db_session.commit()

        response = client.patch(
            f"/api/v1/repair-requests/{rr.id}/repair-details",
            json={"version": rr.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_reject_requires_non_empty_rejection_reason(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_pending_review(db_session, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/reject",
            json={"rejection_reason": "", "version": rr.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_complete_requires_all_repair_detail_fields(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_under_repair(db_session, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/complete",
            json={"version": rr.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_repair_details_rejects_negative_cost(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_under_repair(db_session, holder)
        db_session.commit()

        response = client.patch(
            f"/api/v1/repair-requests/{rr.id}/repair-details",
            json={"repair_cost": "-1.00", "version": rr.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_get_returns_404_for_unknown_id(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        response = client.get(
            "/api/v1/repair-requests/00000000-0000-0000-0000-000000000000",
            headers=auth_headers(manager),
        )
        assert response.status_code == 404


class TestRepairWorkflowAtomicity:
    """A failed commit must roll back both the request and the asset together."""

    def test_approve_rolls_back_both_rows_on_commit_failure(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset, rr = _seed_pending_review(db_session, holder)
        db_session.commit()

        # The endpoint and db_session share the same session via the
        # dependency override in conftest.py; patching the instance method
        # forces _commit_repair_change down its rollback path.
        with patch.object(
            db_session, "commit", side_effect=SQLAlchemyError("boom")
        ):
            response = client.post(
                f"/api/v1/repair-requests/{rr.id}/approve",
                json={"version": rr.version},
                headers=auth_headers(manager),
            )

        assert response.status_code in {500, 503}
        db_session.refresh(rr)
        db_session.refresh(asset)
        assert rr.status == RepairRequestStatus.PENDING_REVIEW
        assert asset.status == AssetStatus.PENDING_REPAIR


class TestSubmitRepairRequest:
    def test_submits_repair_request_and_moves_asset_to_pending_repair(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)

        response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "Screen flickers when connected to HDMI.",
                "version": asset.version,
            },
            headers=auth_headers(holder),
        )

        assert response.status_code == 201
        assert response.headers["location"].startswith("/api/v1/repair-requests/")
        data = response.json()["data"]
        assert data["asset"]["id"] == asset.id
        assert data["requester"]["id"] == holder.id
        assert data["status"] == "pending_review"
        db_session.refresh(asset)
        assert asset.status == AssetStatus.PENDING_REPAIR

    def test_submits_repair_request_from_form_payload_without_version(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)

        response = client.post(
            "/api/v1/repair-requests",
            data={
                "asset_id": asset.id,
                "fault_description": "Screen flickers when connected to HDMI.",
            },
            headers=auth_headers(holder),
        )

        assert response.status_code == 201
        assert response.json()["data"]["asset"]["id"] == asset.id

    def test_json_validation_error_uses_project_error_envelope(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)

        response = client.post(
            "/api/v1/repair-requests",
            json={"asset_id": "not-a-uuid"},
            headers=auth_headers(holder),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        fields = {detail["field"] for detail in response.json()["error"]["details"]}
        assert {"asset_id", "fault_description"}.issubset(fields)

    def test_malformed_json_uses_project_error_envelope(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)

        response = client.post(
            "/api/v1/repair-requests",
            content="{",
            headers={
                **auth_headers(holder),
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "validation_error"
        assert body["error"]["message"] == "Malformed JSON body."

    def test_submits_repair_request_with_image(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)

        response = client.post(
            "/api/v1/repair-requests",
            data={
                "asset_id": asset.id,
                "fault_description": "Screen flickers when connected to HDMI.",
            },
            files=[("images", ("issue.png", _PNG_BYTES, "image/png"))],
            headers=auth_headers(holder),
        )

        assert response.status_code == 201
        images = response.json()["data"]["images"]
        assert len(images) == 1
        assert images[0]["url"] == f"/api/v1/images/{images[0]['id']}"

    def test_submits_repair_request_with_jpeg_image(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)

        response = client.post(
            "/api/v1/repair-requests",
            data={
                "asset_id": asset.id,
                "fault_description": "Screen flickers when connected to HDMI.",
            },
            files=[("images", ("issue.jpg", _JPEG_BYTES, "image/jpeg"))],
            headers=auth_headers(holder),
        )

        assert response.status_code == 201
        assert len(response.json()["data"]["images"]) == 1

    def test_returns_503_when_storage_backend_save_fails(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)
        app.dependency_overrides[get_image_storage] = lambda: FailingImageStorage()

        response = client.post(
            "/api/v1/repair-requests",
            data={
                "asset_id": asset.id,
                "fault_description": "Screen flickers when connected to HDMI.",
            },
            files=[("images", ("issue.png", _PNG_BYTES, "image/png"))],
            headers=auth_headers(holder),
        )

        assert response.status_code == 503
        assert response.json() == {
            "error": {
                "code": "service_unavailable",
                "message": "Unable to store repair images. Please try again later.",
            }
        }

    def test_cleanup_failure_in_finally_does_not_mask_original_503(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # If a future storage backend's cleanup raises (violating the Protocol
        # contract), the finally block must NOT swallow the original 503 and
        # let the cleanup exception bubble as a 500.
        class CleanupRaisesStorage:
            def save(
                self,
                *,
                repair_request_id: str,  # noqa: ARG002
                image_id: str,  # noqa: ARG002
                suffix: str,  # noqa: ARG002
                content: bytes,  # noqa: ARG002
            ) -> str:
                raise ImageStorageError("storage save failed")

            def open(self, storage_key: str) -> tuple[bytes, str]:  # noqa: ARG002
                raise ImageStorageError("not implemented")

            def cleanup(self, storage_keys: list[str]) -> None:  # noqa: ARG002
                raise RuntimeError("cleanup itself blew up")

        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)
        app.dependency_overrides[get_image_storage] = lambda: CleanupRaisesStorage()
        try:
            response = client.post(
                "/api/v1/repair-requests",
                data={
                    "asset_id": asset.id,
                    "fault_description": "Cleanup-failure scenario.",
                },
                files=[("images", ("issue.png", _PNG_BYTES, "image/png"))],
                headers=auth_headers(holder),
            )
        finally:
            app.dependency_overrides.pop(get_image_storage, None)

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_unavailable"

    def test_malformed_json_body_envelope_has_no_details_array(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Pin the manual JSONDecodeError → 422 path's wire shape: it carries
        # `code`/`message` but no `details` array (the failure happens before
        # field-level errors exist). Distinct from FastAPI's RequestValidationError
        # path which does emit `details`.
        holder = make_user(role=UserRole.HOLDER)

        response = client.post(
            "/api/v1/repair-requests",
            content="{",
            headers={
                **auth_headers(holder),
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 422
        body = response.json()["error"]
        assert body["code"] == "validation_error"
        assert body["message"] == "Malformed JSON body."
        assert "details" not in body

    def test_manager_cannot_submit_repair_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)

        response = client.post(
            "/api/v1/repair-requests",
            json={"asset_id": asset.id, "fault_description": "Issue.", "version": asset.version},
            headers=auth_headers(manager),
        )

        assert response.status_code == 403

    def test_rejects_asset_not_in_use(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder, status=AssetStatus.IN_STOCK)

        response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "Screen flickers.",
                "version": asset.version,
            },
            headers=auth_headers(holder),
        )

        assert response.status_code == 409

    def test_rejects_requester_who_does_not_hold_asset(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        other_holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)

        response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "Screen flickers.",
                "version": asset.version,
            },
            headers=auth_headers(other_holder),
        )

        assert response.status_code == 403

    def test_rejects_duplicate_active_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)
        db_session.add(
            RepairRequest(
                asset_id=asset.id,
                requester_id=holder.id,
                status=RepairRequestStatus.PENDING_REVIEW,
                fault_description="Existing issue.",
            )
        )
        db_session.commit()

        response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "New issue.",
                "version": asset.version,
            },
            headers=auth_headers(holder),
        )

        assert response.status_code == 409

    def test_rejects_stale_asset_version(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)

        response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "Screen flickers.",
                "version": asset.version + 1,
            },
            headers=auth_headers(holder),
        )

        assert response.status_code == 409

    def test_returns_404_for_missing_asset(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": "00000000-0000-0000-0000-000000000000",
                "fault_description": "Screen flickers.",
            },
            headers=auth_headers(holder),
        )
        assert response.status_code == 404

    def test_rejects_image_with_disallowed_content_type(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)

        response = client.post(
            "/api/v1/repair-requests",
            data={"asset_id": asset.id, "fault_description": "Cracked screen."},
            files=[("images", ("issue.gif", b"GIF89a-bytes", "image/gif"))],
            headers=auth_headers(holder),
        )
        assert response.status_code == 422

    def test_rejects_image_with_mismatched_content_signature(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)

        response = client.post(
            "/api/v1/repair-requests",
            data={"asset_id": asset.id, "fault_description": "Cracked screen."},
            files=[("images", ("fake.png", b"not-a-real-png", "image/png"))],
            headers=auth_headers(holder),
        )

        assert response.status_code == 422

    def test_rejects_image_above_size_limit(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)
        oversized = b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024)

        response = client.post(
            "/api/v1/repair-requests",
            data={"asset_id": asset.id, "fault_description": "Cracked screen."},
            files=[("images", ("big.png", oversized, "image/png"))],
            headers=auth_headers(holder),
        )
        assert response.status_code == 422

    def test_rejects_more_than_max_images(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)
        files = [
            ("images", (f"img-{i}.png", b"\x89PNG\r\n\x1a\nbytes", "image/png"))
            for i in range(6)
        ]

        response = client.post(
            "/api/v1/repair-requests",
            data={"asset_id": asset.id, "fault_description": "Cracked screen."},
            files=files,
            headers=auth_headers(holder),
        )
        assert response.status_code == 422

    def test_rejects_unsupported_content_type(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)
        body = f'<request><asset_id>{asset.id}</asset_id></request>'.encode()

        response = client.post(
            "/api/v1/repair-requests",
            content=body,
            headers={
                **auth_headers(holder),
                "Content-Type": "application/xml",
            },
        )
        assert response.status_code == 415


class TestSubmitRepairRequestParsingEdges:
    """Pin runtime contract on multipart/form parsing edges that are easy to regress."""

    def test_form_field_value_ending_with_double_dash_is_preserved(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Regression for a multipart parser bug where a field whose value
        # ends with "--" was silently dropped because the parser shortcut
        # `endswith(b"--")` mistook it for the closing-boundary epilogue.
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)

        response = client.post(
            "/api/v1/repair-requests",
            data={
                "asset_id": asset.id,
                "fault_description": "Hyphen-mode failure --",
            },
            headers=auth_headers(holder),
        )

        assert response.status_code == 201
        assert (
            response.json()["data"]["fault_description"] == "Hyphen-mode failure --"
        )

    def test_jpeg_payload_ending_with_end_marker_is_persisted_byte_for_byte(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Regression for binary-content corruption in multipart parsing:
        # a stray `bytes.strip()` would silently chew the trailing 0xFFD9
        # JPEG end marker, breaking later magic-byte validation.
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)
        # Real-shape JPEG: SOI marker + payload + EOI marker.
        jpeg_bytes = b"\xff\xd8" + b"x" * 64 + b"\xff\xd9"

        response = client.post(
            "/api/v1/repair-requests",
            data={"asset_id": asset.id, "fault_description": "Cracked screen."},
            files=[("images", ("issue.jpg", jpeg_bytes, "image/jpeg"))],
            headers=auth_headers(holder),
        )

        assert response.status_code == 201

    def test_multipart_without_boundary_param_returns_422(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        _make_asset(db_session, holder)

        response = client.post(
            "/api/v1/repair-requests",
            content=b"--no-boundary--",
            headers={
                **auth_headers(holder),
                "Content-Type": "multipart/form-data",
            },
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_invalid_content_length_returns_422(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)

        response = client.post(
            "/api/v1/repair-requests",
            content=b"{}",
            headers={
                **auth_headers(holder),
                "Content-Type": "application/json",
                "Content-Length": "not-an-int",
            },
        )

        assert response.status_code == 422

    def test_oversized_content_length_returns_413(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        # Declare a Content-Length above the multipart budget; the body
        # itself is small so the test runs cheaply — the cap fires on the
        # declared length before any buffering happens.
        massive = str(64 * 1024 * 1024)

        response = client.post(
            "/api/v1/repair-requests",
            content=b"--BOUNDARY--",
            headers={
                **auth_headers(holder),
                "Content-Type": "multipart/form-data; boundary=BOUNDARY",
                "Content-Length": massive,
            },
        )

        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"

    def test_form_urlencoded_duplicate_field_returns_422(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Every documented field is scalar — duplicates would silently
        # discard data under a "last wins" rule. Reject with 422.
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)
        body = (
            f"asset_id={asset.id}&"
            f"asset_id={asset.id}&"
            "fault_description=Cracked%20screen."
        ).encode()

        response = client.post(
            "/api/v1/repair-requests",
            content=body,
            headers={
                **auth_headers(holder),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        assert response.status_code == 422
        body_json = response.json()
        assert body_json["error"]["code"] == "validation_error"
        assert "asset_id" in body_json["error"]["message"]


class TestRepairRequest409ErrorCodes:
    """Pin the granular `error.code` values for 409s on the repair-request workflow.

    `docs/system-design/12-api-design.md` distinguishes:
      - `invalid_transition` — FSM precondition violated
      - `duplicate_request`  — an active request already exists for the asset
      - `conflict`           — optimistic-lock version mismatch
    """

    def test_submit_returns_invalid_transition_when_asset_not_in_use(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Desync: holder is still on the asset row but status is no longer in_use.
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder, status=AssetStatus.IN_STOCK)

        response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "Screen flickers.",
                "version": asset.version,
            },
            headers=auth_headers(holder),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_transition"

    def test_submit_returns_duplicate_request_when_active_request_exists(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)
        db_session.add(
            RepairRequest(
                asset_id=asset.id,
                requester_id=holder.id,
                status=RepairRequestStatus.PENDING_REVIEW,
                fault_description="Existing issue.",
            )
        )
        db_session.commit()

        response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "New issue.",
                "version": asset.version,
            },
            headers=auth_headers(holder),
        )

        assert response.status_code == 409
        body = response.json()["error"]
        assert body["code"] == "duplicate_request"
        assert body["message"] == "Repair request already exists for this asset."

    def test_submit_returns_conflict_on_stale_asset_version(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, holder)

        response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "Screen flickers.",
                "version": asset.version + 1,
            },
            headers=auth_headers(holder),
        )

        assert response.status_code == 409
        # Stale-version on submit uses the default `_conflict()` code.
        assert response.json()["error"]["code"] == "conflict"

    def test_approve_returns_invalid_transition_when_request_already_under_repair(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_under_repair(db_session, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/approve",
            json={"version": rr.version},
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_transition"

    def test_complete_returns_invalid_transition_when_request_still_pending_review(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_pending_review(db_session, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/complete",
            json=_complete_payload(rr.version),
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_transition"

    def test_complete_returns_conflict_on_stale_request_version(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_under_repair(db_session, holder)
        db_session.commit()

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/complete",
            json=_complete_payload(rr.version + 1),
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_repair_details_returns_invalid_transition_when_request_in_pending_review(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _, rr = _seed_pending_review(db_session, holder)
        db_session.commit()

        response = client.patch(
            f"/api/v1/repair-requests/{rr.id}/repair-details",
            json=_details_payload(rr.version),
            headers=auth_headers(manager),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_transition"
