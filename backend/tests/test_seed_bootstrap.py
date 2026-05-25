"""Verify the demo-seed script includes the bootstrap manager (Decision A2)."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import get_args

import pytest

from app.core.config import get_settings
from app.core.security import verify_password
from app.models.asset import Asset, AssetStatus
from app.models.asset_action_history import AssetAction, AssetActionHistory
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole
from app.schemas.asset import AssetCategory
from scripts.seed_demo_data import (
    CATEGORIES,
    build_action_histories,
    build_assets,
    build_bootstrap_manager,
    build_images,
    build_repair_requests,
    build_users,
)


def _prime_ids(*collections: Iterable[Asset | User | RepairRequest]) -> None:
    """Assign UUIDs to in-memory ORM objects so cross-table lookups work.

    The model column defaults only fire at flush, but the seed builders run
    standalone in these tests — without primed IDs, ``repair_request.asset_id``
    and friends would all be None.
    """
    for collection in collections:
        for obj in collection:
            if getattr(obj, "id", None) is None:
                obj.id = str(uuid.uuid4())


@dataclass(frozen=True)
class _Seeded:
    assets: list[Asset]
    repair_requests: list[RepairRequest]
    histories: list[AssetActionHistory]
    holders: list[User]
    managers: list[User]


class TestBootstrapManager:
    def test_build_bootstrap_manager_matches_settings(self) -> None:
        settings = get_settings()
        user = build_bootstrap_manager()
        assert user.email == settings.bootstrap_manager_email
        assert user.role is UserRole.MANAGER
        assert user.name == settings.bootstrap_manager_name
        assert user.department == settings.bootstrap_manager_department
        # Password is stored hashed, verifies against the configured plaintext.
        assert verify_password(
            settings.bootstrap_manager_password.get_secret_value(),
            user.password_hash,
        )

    def test_build_users_contains_bootstrap_manager(self) -> None:
        settings = get_settings()
        users = build_users()
        emails = {u.email for u in users}
        assert settings.bootstrap_manager_email in emails

    def test_build_users_dedupes_when_bootstrap_collides_with_demo_email(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Without the collision guard this would raise a unique-constraint
        # error on flush; with the guard, the demo manager1 entry is skipped
        # and the bootstrap row keeps the email.
        monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "manager1@example.com")
        get_settings.cache_clear()
        try:
            users = build_users()
            emails = [u.email for u in users]
            assert len(emails) == len(set(emails)), f"duplicate emails: {emails}"
            assert "manager1@example.com" in emails
            assert "manager2@example.com" in emails
            assert "holder1@example.com" in emails
        finally:
            get_settings.cache_clear()


class TestSeedActionHistories:
    @pytest.fixture
    def seeded(self) -> _Seeded:
        users = build_users()
        _prime_ids(users)
        holders = [u for u in users if u.role == UserRole.HOLDER]
        managers = [u for u in users if u.role == UserRole.MANAGER]
        assets = build_assets(holders)
        _prime_ids(assets)
        repair_requests = build_repair_requests(assets, holders, managers)
        _prime_ids(repair_requests)
        histories = build_action_histories(assets, repair_requests, holders, managers)
        return _Seeded(
            assets=assets,
            repair_requests=repair_requests,
            histories=histories,
            holders=holders,
            managers=managers,
        )

    def test_in_stock_assets_have_no_history(self, seeded: _Seeded) -> None:
        # FSM T1 is exempt — IN_STOCK assets only carry their created_at.
        in_stock_ids = {a.id for a in seeded.assets if a.status is AssetStatus.IN_STOCK}
        assert in_stock_ids, "expected at least one IN_STOCK asset in the seed"
        for history in seeded.histories:
            assert history.asset_id not in in_stock_ids

    def test_disposed_assets_have_dispose_history(self, seeded: _Seeded) -> None:
        disposed_assets = [a for a in seeded.assets if a.status is AssetStatus.DISPOSED]
        disposed_ids = {a.id for a in disposed_assets}
        assert disposed_ids, "expected at least one DISPOSED asset in the seed"
        disposal_reasons = {a.id: a.disposal_reason for a in disposed_assets}
        dispose_history = [h for h in seeded.histories if h.action is AssetAction.DISPOSE]
        assert {h.asset_id for h in dispose_history} == disposed_ids
        for history in dispose_history:
            assert history.from_status == AssetStatus.IN_STOCK.value
            assert history.to_status == AssetStatus.DISPOSED.value
            assert history.event_metadata == {"disposal_reason": disposal_reasons[history.asset_id]}

    def test_repair_request_lifecycle_matches_status(self, seeded: _Seeded) -> None:
        # Each repair-request status implies a fixed action sequence per
        # docs/system-design/11-asset-fsm.md; assert one example of each.
        expected_per_status = {
            "pending_review": {"assign", "submit_repair"},
            "under_repair": {"assign", "submit_repair", "approve_repair"},
            "completed": {
                "assign",
                "submit_repair",
                "approve_repair",
                "complete_repair",
            },
            "rejected": {"assign", "submit_repair", "reject_repair"},
        }
        by_asset: dict[str, list[str]] = {}
        for history in seeded.histories:
            by_asset.setdefault(history.asset_id, []).append(history.action.value)

        seen_statuses: set[str] = set()
        for repair_request in seeded.repair_requests:
            actions = set(by_asset[repair_request.asset_id])
            assert actions == expected_per_status[repair_request.status.value], (
                f"asset {repair_request.asset_id} (rr status="
                f"{repair_request.status.value}) has actions {actions}"
            )
            seen_statuses.add(repair_request.status.value)
        assert seen_statuses == set(expected_per_status), (
            f"seed missing coverage for repair statuses: {set(expected_per_status) - seen_statuses}"
        )

    def test_action_counts_match_fsm_implication(self, seeded: _Seeded) -> None:
        # Sanity-check totals so a future cycle change doesn't silently
        # under- or over-seed the audit trail.
        counts = Counter(h.action.value for h in seeded.histories)
        assigns = sum(
            1
            for a in seeded.assets
            if a.status is not AssetStatus.IN_STOCK and a.status is not AssetStatus.DISPOSED
        )
        assert counts["assign"] == assigns
        assert counts["submit_repair"] == len(seeded.repair_requests)
        assert counts["dispose"] == sum(
            1 for a in seeded.assets if a.status is AssetStatus.DISPOSED
        )


class TestSeedCategories:
    def test_seed_categories_match_asset_category_literal(self) -> None:
        # The API ``AssetCategory`` Literal is the contract; the seed must not
        # drift from it. ``Asset.category`` is ``String(100)`` so a mismatch
        # would silently insert and then break every write + filter.
        allowed = set(get_args(AssetCategory))
        assert set(CATEGORIES) <= allowed, (
            f"seed categories not in AssetCategory: {set(CATEGORIES) - allowed}"
        )

    def test_built_assets_only_use_canonical_categories(self) -> None:
        users = build_users()
        _prime_ids(users)
        holders = [u for u in users if u.role == UserRole.HOLDER]
        assets = build_assets(holders)
        allowed = set(get_args(AssetCategory))
        offenders = {a.category for a in assets} - allowed
        assert not offenders, f"non-canonical categories in seed: {offenders}"


class TestSeedDemoRealism:
    def test_build_users_has_believable_demo_population(self) -> None:
        users = build_users()

        managers = [u for u in users if u.role is UserRole.MANAGER]
        holders = [u for u in users if u.role is UserRole.HOLDER]
        assert len(managers) >= 4
        assert len(holders) == 10
        assert {"陳怡君", "王志豪", "李欣穎"} <= {u.name for u in managers}
        assert "Holder 1" not in {u.name for u in holders}

    def test_build_assets_uses_model_names_and_bound_suppliers(self) -> None:
        users = build_users()
        _prime_ids(users)
        holders = [u for u in users if u.role == UserRole.HOLDER]

        assets = build_assets(holders)

        assert len([a for a in assets if a.status is not AssetStatus.DISPOSED]) == 60
        assert len([a for a in assets if a.status is AssetStatus.DISPOSED]) == 3
        assert "Business Laptop" not in {a.name for a in assets}
        assert "Company Phone" not in {a.name for a in assets}
        assert any(a.name == "MacBook Pro 14 M3" and a.supplier == "Apple" for a in assets)
        assert any("Fab12" in a.location for a in assets)

    def test_repair_requests_have_explicit_fsm_distribution_and_realistic_content(
        self,
    ) -> None:
        users = build_users()
        _prime_ids(users)
        holders = [u for u in users if u.role == UserRole.HOLDER]
        managers = [u for u in users if u.role == UserRole.MANAGER]
        assets = build_assets(holders)
        _prime_ids(assets)

        repair_requests = build_repair_requests(assets, holders, managers)

        assert Counter(rr.status for rr in repair_requests) == {
            RepairRequestStatus.PENDING_REVIEW: 3,
            RepairRequestStatus.UNDER_REPAIR: 3,
            RepairRequestStatus.COMPLETED: 4,
            RepairRequestStatus.REJECTED: 2,
        }
        assert not any("Issue" in rr.fault_description for rr in repair_requests)
        assert not any(
            rr.fault_content == f"Verified issue for {rr.asset_id}" for rr in repair_requests
        )
        assert "FixIt Services" not in {rr.repair_vendor for rr in repair_requests}

        detailed_requests = [
            rr
            for rr in repair_requests
            if rr.status in {RepairRequestStatus.UNDER_REPAIR, RepairRequestStatus.COMPLETED}
        ]
        assert {rr.repair_vendor for rr in detailed_requests} >= {
            "聯強國際維修中心",
            "內部 IT 維護組",
        }
        repair_costs = [rr.repair_cost for rr in detailed_requests]
        assert repair_costs != [
            repair_costs[0] + (index * Decimal("10.00"))
            for index in range(len(repair_costs))
        ]


class TestSeedRepairImages:
    def test_build_images_writes_storage_key_backed_demo_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REPAIR_UPLOAD_DIR", str(tmp_path))
        get_settings.cache_clear()
        try:
            repair_request = RepairRequest(id="repair-request-1")

            images = build_images([repair_request])

            assert len(images) == 1
            image = images[0]
            assert image.image_url == f"{repair_request.id}/{image.id}.jpg"
            assert not image.image_url.startswith("/")
            assert (tmp_path / image.image_url).read_bytes().startswith(b"\xff\xd8")
        finally:
            get_settings.cache_clear()

    def test_build_images_prefers_active_or_completed_repairs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REPAIR_UPLOAD_DIR", str(tmp_path))
        get_settings.cache_clear()
        try:
            requests = [
                RepairRequest(id="pending", status=RepairRequestStatus.PENDING_REVIEW),
                RepairRequest(id="rejected", status=RepairRequestStatus.REJECTED),
                RepairRequest(id="under", status=RepairRequestStatus.UNDER_REPAIR),
                RepairRequest(id="completed", status=RepairRequestStatus.COMPLETED),
            ]

            images = build_images(requests)

            assert {image.repair_request_id for image in images} == {"under", "completed"}
        finally:
            get_settings.cache_clear()
