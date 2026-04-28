from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole

_PURCHASE_DATE = date(2026, 1, 1)


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
            files=[("images", ("issue.png", b"png-bytes", "image/png"))],
            headers=auth_headers(holder),
        )

        assert response.status_code == 201
        images = response.json()["data"]["images"]
        assert len(images) == 1
        assert images[0]["url"].endswith(".png")

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
