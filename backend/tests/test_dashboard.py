from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole

_PURCHASE_DATE = date(2026, 1, 1)


def _next_repair_id() -> str:
    # uuid4 hex avoids the cross-test counter collisions that used to
    # surface as opaque IntegrityError when pytest reordered classes.
    return f"REP-2026-{uuid.uuid4().hex[:10].upper()}"


def _next_asset_code() -> str:
    return f"AST-2026-{uuid.uuid4().hex[:10].upper()}"


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
            "in_stock_assets": 0,
            "in_use_assets": 0,
            "pending_repair_assets": 0,
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
        # Two days back, well outside the today boundary; the name avoids
        # the trap of someone changing this to a one-day delta and silently
        # crossing midnight in test runs near UTC 00:00.
        past = now - timedelta(days=2)

        _make_repair_request(db_session, asset, holder, created_at=now)
        _make_repair_request(db_session, asset, holder, created_at=now)
        # Older pending row — used to confirm `pending_review` is a
        # snapshot (status-only) and not time-bounded by "today".
        _make_repair_request(
            db_session,
            asset,
            holder,
            status=RepairRequestStatus.REJECTED,
            created_at=past,
        )

        _make_repair_request(
            db_session, asset, holder, status=RepairRequestStatus.UNDER_REPAIR, created_at=past
        )

        _make_repair_request(
            db_session,
            asset,
            holder,
            status=RepairRequestStatus.COMPLETED,
            completed_at=now,
            created_at=past,
        )
        _make_repair_request(
            db_session,
            asset,
            holder,
            status=RepairRequestStatus.COMPLETED,
            completed_at=past,
            created_at=past,
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

    def test_join_pairs_each_row_with_its_own_asset_and_requester(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Single-row tests cannot catch a swapped join predicate; this
        # fixture has different asset/requester per pending request so
        # any cross-row leakage shows up as a name/asset mismatch.
        manager = make_user(role=UserRole.MANAGER)
        holder_a = make_user(role=UserRole.HOLDER, name="Alice")
        holder_b = make_user(role=UserRole.HOLDER, name="Bob")
        asset_a = _make_asset(db_session, status=AssetStatus.IN_USE, holder=holder_a)
        asset_a.name = "Laptop A"
        asset_b = _make_asset(db_session, status=AssetStatus.IN_USE, holder=holder_b)
        asset_b.name = "Monitor B"
        db_session.flush()

        now = datetime.now(UTC)
        rr_a = _make_repair_request(
            db_session, asset_a, holder_a, created_at=now - timedelta(minutes=5)
        )
        rr_b = _make_repair_request(
            db_session, asset_b, holder_b, created_at=now - timedelta(minutes=1)
        )
        db_session.commit()

        response = client.get("/api/v1/dashboard/manager", headers=auth_headers(manager))
        recents = response.json()["data"]["recent_pending_repairs"]
        by_id = {r["repair_id"]: r for r in recents}
        assert by_id[rr_a.repair_id]["asset_name"] == "Laptop A"
        assert by_id[rr_a.repair_id]["requester_name"] == "Alice"
        assert by_id[rr_b.repair_id]["asset_name"] == "Monitor B"
        assert by_id[rr_b.repair_id]["requester_name"] == "Bob"

    def test_created_at_is_serialized_with_explicit_utc_offset(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_USE, holder=holder)
        _make_repair_request(db_session, asset, holder, created_at=datetime.now(UTC))
        db_session.commit()

        response = client.get("/api/v1/dashboard/manager", headers=auth_headers(manager))
        recents = response.json()["data"]["recent_pending_repairs"]
        assert len(recents) == 1
        # AwareDatetime serialises with an offset; "+00:00" or "Z" both
        # signal UTC. A bare timestamp without offset would mean the
        # naive MySQL value leaked through.
        ts = recents[0]["created_at"]
        assert ts.endswith("+00:00") or ts.endswith("Z"), ts


class TestDashboardTodayBoundary:
    def test_row_one_microsecond_before_today_is_excluded(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_USE, holder=holder)
        today_start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
        _make_repair_request(
            db_session,
            asset,
            holder,
            created_at=today_start - timedelta(microseconds=1),
        )
        db_session.commit()

        response = client.get("/api/v1/dashboard/manager", headers=auth_headers(manager))
        assert response.json()["data"]["repair_summary"]["created_today"] == 0

    def test_row_exactly_at_today_start_is_included(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_USE, holder=holder)
        today_start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
        _make_repair_request(db_session, asset, holder, created_at=today_start)
        db_session.commit()

        response = client.get("/api/v1/dashboard/manager", headers=auth_headers(manager))
        assert response.json()["data"]["repair_summary"]["created_today"] == 1


class TestDashboardPendingReviewInvariant:
    def test_kpi_pending_repair_requests_equals_summary_pending_review(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Locks in the invariant that the two PENDING_REVIEW values are
        # sourced from the same row, so a future refactor cannot make
        # them drift.
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session, status=AssetStatus.IN_USE, holder=holder)
        for _ in range(3):
            _make_repair_request(
                db_session, asset, holder, status=RepairRequestStatus.PENDING_REVIEW
            )
        _make_repair_request(
            db_session, asset, holder, status=RepairRequestStatus.UNDER_REPAIR
        )
        db_session.commit()

        response = client.get("/api/v1/dashboard/manager", headers=auth_headers(manager))
        data = response.json()["data"]
        assert (
            data["kpis"]["pending_repair_requests"]
            == data["repair_summary"]["pending_review"]
            == 3
        )


class TestDashboard503:
    def test_sqlalchemy_error_returns_503_envelope_with_granular_code(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)

        from sqlalchemy.orm import Session as _SASession

        def _boom(self: _SASession, *args: object, **kwargs: object) -> object:
            raise OperationalError("forced failure", params=None, orig=Exception("db down"))

        monkeypatch.setattr(_SASession, "execute", _boom)

        response = client.get("/api/v1/dashboard/manager", headers=auth_headers(manager))
        assert response.status_code == 503
        body = response.json()
        assert body == {
            "error": {
                "code": "dashboard_unavailable",
                "message": "Unable to load dashboard. Please try again later.",
            }
        }
