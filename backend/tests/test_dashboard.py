from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole

_PURCHASE_DATE = date(2026, 1, 1)
_REPAIR_ID_COUNTER = itertools.count(1)
_ASSET_CODE_COUNTER = itertools.count(1)


def _next_repair_id() -> str:
    return f"REP-2026-{next(_REPAIR_ID_COUNTER):05d}"


def _next_asset_code() -> str:
    return f"AST-2026-{next(_ASSET_CODE_COUNTER):05d}"


def _make_asset(
    session: Session,
    *,
    category: str = "computer",
    status: AssetStatus = AssetStatus.IN_STOCK,
    holder: User | None = None,
) -> Asset:
    asset = Asset(
        asset_code=_next_asset_code(),
        name="Test Asset",
        model="Test Model",
        category=category,
        supplier="Test Supplier",
        purchase_date=_PURCHASE_DATE,
        purchase_amount=Decimal("1000.00"),
        location="Taipei HQ",
        department="IT",
        status=status,
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
    created_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> RepairRequest:
    rr = RepairRequest(
        asset_id=asset.id,
        repair_id=_next_repair_id(),
        requester_id=requester.id,
        status=status,
        fault_description="Screen flickers.",
        completed_at=completed_at,
    )
    session.add(rr)
    session.flush()
    if created_at is not None:
        rr.created_at = created_at
        session.flush()
    return rr


class TestDashboardAuth:
    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        response = client.get("/api/v1/dashboard/manager")
        assert response.status_code == 401

    def test_holder_forbidden(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        response = client.get("/api/v1/dashboard/manager", headers=auth_headers(holder))
        assert response.status_code == 403


class TestDashboardEmpty:
    def test_empty_db_returns_zeroed_payload(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        response = client.get("/api/v1/dashboard/manager", headers=auth_headers(manager))
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["kpis"] == {
            "total_assets": 0,
            "in_use_assets": 0,
            "under_repair_assets": 0,
            "pending_repair_requests": 0,
        }
        assert body["asset_categories"] == []
        assert body["repair_summary"] == {
            "created_today": 0,
            "pending_review": 0,
            "under_repair": 0,
            "completed_today": 0,
        }
        assert body["recent_pending_repairs"] == []


class TestDashboardKpis:
    def test_kpis_exclude_disposed_assets(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        _make_asset(db_session, status=AssetStatus.IN_USE, holder=holder)
        _make_asset(db_session, status=AssetStatus.IN_USE, holder=holder)
        _make_asset(db_session, status=AssetStatus.UNDER_REPAIR)
        _make_asset(db_session, status=AssetStatus.IN_STOCK)
        _make_asset(db_session, status=AssetStatus.DISPOSED)
        db_session.commit()

        response = client.get("/api/v1/dashboard/manager", headers=auth_headers(manager))
        assert response.status_code == 200
        kpis = response.json()["data"]["kpis"]
        assert kpis["total_assets"] == 4
        assert kpis["in_use_assets"] == 2
        assert kpis["under_repair_assets"] == 1

    def test_pending_repair_requests_counts_only_pending_review(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_USE, holder=holder)
        _make_repair_request(db_session, asset, holder, status=RepairRequestStatus.PENDING_REVIEW)
        _make_repair_request(db_session, asset, holder, status=RepairRequestStatus.PENDING_REVIEW)
        _make_repair_request(db_session, asset, holder, status=RepairRequestStatus.UNDER_REPAIR)
        _make_repair_request(db_session, asset, holder, status=RepairRequestStatus.COMPLETED)
        _make_repair_request(db_session, asset, holder, status=RepairRequestStatus.REJECTED)
        db_session.commit()

        response = client.get("/api/v1/dashboard/manager", headers=auth_headers(manager))
        assert response.json()["data"]["kpis"]["pending_repair_requests"] == 2


class TestDashboardAssetCategories:
    def test_groups_by_category_excludes_disposed_sorted_by_count_desc(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        for _ in range(3):
            _make_asset(db_session, category="computer")
        for _ in range(2):
            _make_asset(db_session, category="monitor")
        _make_asset(db_session, category="keyboard")
        _make_asset(db_session, category="computer", status=AssetStatus.DISPOSED)
        db_session.commit()

        response = client.get("/api/v1/dashboard/manager", headers=auth_headers(manager))
        categories = response.json()["data"]["asset_categories"]
        assert categories == [
            {"category": "computer", "count": 3},
            {"category": "monitor", "count": 2},
            {"category": "keyboard", "count": 1},
        ]


class TestDashboardRepairSummary:
    def test_created_today_and_completed_today_use_today_boundary(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_USE, holder=holder)

        now = datetime.now(UTC)
        yesterday = now - timedelta(days=2)

        _make_repair_request(db_session, asset, holder, created_at=now)
        _make_repair_request(db_session, asset, holder, created_at=now)
        _make_repair_request(db_session, asset, holder, created_at=yesterday)

        _make_repair_request(
            db_session, asset, holder, status=RepairRequestStatus.UNDER_REPAIR, created_at=yesterday
        )

        _make_repair_request(
            db_session,
            asset,
            holder,
            status=RepairRequestStatus.COMPLETED,
            completed_at=now,
            created_at=yesterday,
        )
        _make_repair_request(
            db_session,
            asset,
            holder,
            status=RepairRequestStatus.COMPLETED,
            completed_at=yesterday,
            created_at=yesterday,
        )
        db_session.commit()

        response = client.get("/api/v1/dashboard/manager", headers=auth_headers(manager))
        summary = response.json()["data"]["repair_summary"]
        assert summary["created_today"] == 2
        assert summary["pending_review"] == 2
        assert summary["under_repair"] == 1
        assert summary["completed_today"] == 1


class TestDashboardRecentPending:
    def test_returns_up_to_three_most_recent_pending_with_joined_names(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER, name="陳美華")
        asset = _make_asset(db_session, status=AssetStatus.IN_USE, holder=holder)
        asset.name = "MacBook Pro 14"
        db_session.flush()

        now = datetime.now(UTC)
        for i in range(4):
            _make_repair_request(
                db_session, asset, holder, created_at=now - timedelta(minutes=10 - i)
            )
        _make_repair_request(
            db_session, asset, holder, status=RepairRequestStatus.UNDER_REPAIR, created_at=now
        )
        db_session.commit()

        response = client.get("/api/v1/dashboard/manager", headers=auth_headers(manager))
        recents = response.json()["data"]["recent_pending_repairs"]
        assert len(recents) == 3
        first = recents[0]
        assert first["asset_name"] == "MacBook Pro 14"
        assert first["requester_name"] == "陳美華"
        assert first["status"] == "pending_review"
        assert {"id", "repair_id", "asset_id", "created_at"}.issubset(first.keys())
        timestamps = [r["created_at"] for r in recents]
        assert timestamps == sorted(timestamps, reverse=True)
