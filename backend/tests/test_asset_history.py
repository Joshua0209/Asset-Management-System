from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.asset_action_history import (
    AssetAction,
    AssetActionHistory,
)
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole
from app.services.audit_log import record_asset_action

# Realistic fixture data shared across the suite.
_PURCHASE_DATE = date(2026, 1, 1)
_REPAIR_DATE = date(2026, 4, 20)


def _make_asset(
    session: Session,
    *,
    asset_code: str = "AST-2026-00001",
    status: AssetStatus = AssetStatus.IN_STOCK,
    responsible_person_id: str | None = None,
    deleted_at: datetime | None = None,
) -> Asset:
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
        status=status,
        responsible_person_id=responsible_person_id,
        deleted_at=deleted_at,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def _make_repair_request(
    session: Session,
    *,
    asset: Asset,
    requester: User,
    status: RepairRequestStatus = RepairRequestStatus.PENDING_REVIEW,
) -> RepairRequest:
    rr = RepairRequest(
        asset_id=asset.id,
        requester_id=requester.id,
        status=status,
        fault_description="Screen flickers.",
    )
    session.add(rr)
    session.commit()
    session.refresh(rr)
    return rr


def _history_for(session: Session, asset_id: str) -> list[AssetActionHistory]:
    return list(
        session.scalars(
            select(AssetActionHistory)
            .where(AssetActionHistory.asset_id == asset_id)
            .order_by(AssetActionHistory.created_at.asc())
        )
    )


class TestModelMetadataInvariant:
    """Guard the SQLAlchemy gotcha: a column named ``metadata`` must not shadow
    ``Base.metadata`` on the model class. The Python attribute is
    ``event_metadata`` and the SQL column is ``metadata``."""

    def test_python_attribute_is_event_metadata_not_metadata(self) -> None:
        attr_names = {col.key for col in AssetActionHistory.__mapper__.column_attrs}
        assert "event_metadata" in attr_names
        assert "metadata" not in attr_names, (
            "Naming the Python attr 'metadata' collides with Base.metadata"
        )

    def test_sql_column_name_is_metadata(self) -> None:
        column = AssetActionHistory.__table__.columns["metadata"]
        assert column is not None

    def test_no_updated_or_deleted_or_version_columns(self) -> None:
        # Append-only audit rows: they are never updated or soft-deleted, and
        # carry no optimistic-lock version.
        col_names = {c.name for c in AssetActionHistory.__table__.columns}
        for forbidden in ("updated_at", "deleted_at", "version"):
            assert forbidden not in col_names, (
                f"asset_action_histories must not have {forbidden}"
            )

    def test_round_trip_through_session(self, db_session: Session) -> None:
        # If create_all built the table correctly, a basic insert+select works.
        asset = _make_asset(db_session)
        actor = User(
            email="actor@example.com",
            password_hash="x",
            name="Actor",
            role=UserRole.MANAGER,
            department="IT",
        )
        db_session.add(actor)
        db_session.commit()

        history = AssetActionHistory(
            asset_id=asset.id,
            actor_id=actor.id,
            action=AssetAction.ASSIGN.value,
            from_status=AssetStatus.IN_STOCK.value,
            to_status=AssetStatus.IN_USE.value,
            event_metadata={"responsible_person_id": actor.id},
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(history)

        assert history.id is not None
        assert history.created_at is not None
        assert history.event_metadata == {"responsible_person_id": actor.id}


class TestAuditLogService:
    def test_record_asset_action_adds_row_without_committing(
        self,
        db_session: Session,
    ) -> None:
        asset = _make_asset(db_session)
        actor = User(
            email="manager@example.com",
            password_hash="x",
            name="Manager",
            role=UserRole.MANAGER,
            department="IT",
        )
        db_session.add(actor)
        db_session.commit()

        before = len(_history_for(db_session, asset.id))

        history = record_asset_action(
            db_session,
            asset=asset,
            actor=actor,
            action=AssetAction.DISPOSE,
            from_status=AssetStatus.IN_STOCK,
            to_status=AssetStatus.DISPOSED,
            metadata={"disposal_reason": "End of life"},
        )

        # Row exists in session but not yet flushed/committed by the service.
        assert history in db_session.new or history.id is not None
        # Pending state visible only inside this transaction.
        db_session.flush()
        in_session = _history_for(db_session, asset.id)
        assert len(in_session) == before + 1
        latest = in_session[-1]
        assert latest.action == AssetAction.DISPOSE.value
        assert latest.event_metadata == {"disposal_reason": "End of life"}


def _login(
    holder: User,
    auth_headers: Callable[[User], dict[str, str]],
) -> dict[str, str]:
    return auth_headers(holder)


class TestTransitionsRecordHistory:
    """Per-FSM-transition integration tests: drive each endpoint, assert
    exactly one history row was written with correct payload."""

    def test_assign_records_history(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER, name="Alice")
        asset = _make_asset(db_session)

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={"responsible_person_id": holder.id, "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 200, response.text

        events = _history_for(db_session, asset.id)
        assert len(events) == 1
        ev = events[0]
        assert ev.action == AssetAction.ASSIGN.value
        assert ev.from_status == AssetStatus.IN_STOCK.value
        assert ev.to_status == AssetStatus.IN_USE.value
        assert ev.actor_id == manager.id
        assert ev.event_metadata is not None
        assert ev.event_metadata["responsible_person_id"] == holder.id

    def test_unassign_records_history_with_previous_holder(
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
            json={"reason": "End of project", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 200, response.text

        events = _history_for(db_session, asset.id)
        assert len(events) == 1
        ev = events[0]
        assert ev.action == AssetAction.UNASSIGN.value
        assert ev.from_status == AssetStatus.IN_USE.value
        assert ev.to_status == AssetStatus.IN_STOCK.value
        assert ev.actor_id == manager.id
        assert ev.event_metadata is not None
        assert ev.event_metadata["reason"] == "End of project"
        assert ev.event_metadata["previous_responsible_person_id"] == holder.id

    def test_dispose_records_history(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)  # IN_STOCK, no holder

        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "Beyond economical repair", "version": asset.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 200, response.text

        events = _history_for(db_session, asset.id)
        assert len(events) == 1
        ev = events[0]
        assert ev.action == AssetAction.DISPOSE.value
        assert ev.from_status == AssetStatus.IN_STOCK.value
        assert ev.to_status == AssetStatus.DISPOSED.value
        assert ev.event_metadata is not None
        assert ev.event_metadata["disposal_reason"] == "Beyond economical repair"

    def test_submit_repair_records_history(
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
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "Won't power on after a fall.",
                "version": asset.version,
            },
            headers=auth_headers(holder),
        )
        assert response.status_code == 201, response.text

        events = _history_for(db_session, asset.id)
        assert len(events) == 1
        ev = events[0]
        assert ev.action == AssetAction.SUBMIT_REPAIR.value
        assert ev.from_status == AssetStatus.IN_USE.value
        assert ev.to_status == AssetStatus.PENDING_REPAIR.value
        assert ev.actor_id == holder.id
        assert ev.event_metadata is not None
        assert "repair_request_id" in ev.event_metadata
        assert ev.event_metadata["fault_description"] == "Won't power on after a fall."

    def test_approve_repair_records_history(
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
            status=AssetStatus.PENDING_REPAIR,
            responsible_person_id=holder.id,
        )
        rr = _make_repair_request(db_session, asset=asset, requester=holder)

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/approve",
            json={"version": rr.version},
            headers=auth_headers(manager),
        )
        assert response.status_code == 200, response.text

        events = _history_for(db_session, asset.id)
        assert len(events) == 1
        ev = events[0]
        assert ev.action == AssetAction.APPROVE_REPAIR.value
        assert ev.from_status == AssetStatus.PENDING_REPAIR.value
        assert ev.to_status == AssetStatus.UNDER_REPAIR.value
        assert ev.actor_id == manager.id
        assert ev.event_metadata is not None
        assert ev.event_metadata["repair_request_id"] == rr.id

    def test_reject_repair_records_history(
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
            status=AssetStatus.PENDING_REPAIR,
            responsible_person_id=holder.id,
        )
        rr = _make_repair_request(db_session, asset=asset, requester=holder)

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/reject",
            json={
                "version": rr.version,
                "rejection_reason": "Out of warranty and not cost-effective.",
            },
            headers=auth_headers(manager),
        )
        assert response.status_code == 200, response.text

        events = _history_for(db_session, asset.id)
        assert len(events) == 1
        ev = events[0]
        assert ev.action == AssetAction.REJECT_REPAIR.value
        assert ev.from_status == AssetStatus.PENDING_REPAIR.value
        assert ev.to_status == AssetStatus.IN_USE.value
        assert ev.actor_id == manager.id
        assert ev.event_metadata is not None
        assert (
            ev.event_metadata["rejection_reason"]
            == "Out of warranty and not cost-effective."
        )
        assert ev.event_metadata["repair_request_id"] == rr.id

    def test_complete_repair_records_history(
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
            status=AssetStatus.UNDER_REPAIR,
            responsible_person_id=holder.id,
        )
        rr = _make_repair_request(
            db_session,
            asset=asset,
            requester=holder,
            status=RepairRequestStatus.UNDER_REPAIR,
        )

        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/complete",
            json={
                "version": rr.version,
                "repair_date": _REPAIR_DATE.isoformat(),
                "fault_content": "Fan failure",
                "repair_plan": "Replaced fan",
                "repair_cost": "1234.56",
                "repair_vendor": "Acme Repair",
            },
            headers=auth_headers(manager),
        )
        assert response.status_code == 200, response.text

        events = _history_for(db_session, asset.id)
        assert len(events) == 1
        ev = events[0]
        assert ev.action == AssetAction.COMPLETE_REPAIR.value
        assert ev.from_status == AssetStatus.UNDER_REPAIR.value
        assert ev.to_status == AssetStatus.IN_USE.value
        assert ev.actor_id == manager.id
        assert ev.event_metadata is not None
        assert ev.event_metadata["repair_request_id"] == rr.id
        # Decimal must JSON-encode cleanly: stored as string per the plan.
        assert ev.event_metadata["repair_cost"] == "1234.56"
        assert ev.event_metadata["repair_vendor"] == "Acme Repair"


class TestHistoryEndpoint:
    def test_returns_history_sorted_desc_with_pagination_meta(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session)

        # Drive a 3-event history: assign → unassign → dispose
        client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={"responsible_person_id": holder.id, "version": asset.version},
            headers=auth_headers(manager),
        )
        db_session.refresh(asset)
        client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={"reason": "Returned", "version": asset.version},
            headers=auth_headers(manager),
        )
        db_session.refresh(asset)
        client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            json={"disposal_reason": "Damaged beyond repair", "version": asset.version},
            headers=auth_headers(manager),
        )

        response = client.get(
            f"/api/v1/assets/{asset.id}/history",
            headers=auth_headers(manager),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        actions = [event["action"] for event in body["data"]]
        assert actions == ["dispose", "unassign", "assign"]
        meta = body["meta"]
        assert meta["total"] == 3
        assert meta["page"] == 1
        assert meta["per_page"] == 20
        # The response shape must expose the SQL-side `metadata` key (not
        # the SQLAlchemy attr `event_metadata`).
        first = body["data"][0]
        assert "metadata" in first
        assert "event_metadata" not in first
        assert first["actor"] == {"id": manager.id, "name": manager.name}

    def test_holder_cannot_read_history(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session)

        response = client.get(
            f"/api/v1/assets/{asset.id}/history",
            headers=auth_headers(holder),
        )
        assert response.status_code == 403

    def test_unauthenticated_returns_401(
        self,
        client: TestClient,
        db_session: Session,
    ) -> None:
        asset = _make_asset(db_session)
        response = client.get(f"/api/v1/assets/{asset.id}/history")
        assert response.status_code == 401

    def test_unknown_asset_returns_404(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        unknown = "00000000-0000-0000-0000-000000000000"
        response = client.get(
            f"/api/v1/assets/{unknown}/history",
            headers=auth_headers(manager),
        )
        assert response.status_code == 404

    def test_malformed_uuid_returns_422(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        response = client.get(
            "/api/v1/assets/not-a-uuid/history",
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_soft_deleted_asset_returns_history(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Confirmed design choice: audit trail outlives the asset row.
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)
        # Seed one history row, then soft-delete the asset.
        record_asset_action(
            db_session,
            asset=asset,
            actor=manager,
            action=AssetAction.DISPOSE,
            from_status=AssetStatus.IN_STOCK,
            to_status=AssetStatus.DISPOSED,
            metadata={"disposal_reason": "test"},
        )
        asset.deleted_at = datetime.now(UTC)
        db_session.commit()

        response = client.get(
            f"/api/v1/assets/{asset.id}/history",
            headers=auth_headers(manager),
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_soft_deleted_actor_renders_as_null(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Confirmed design choice: actor: null after the user is soft-deleted.
        manager = make_user(role=UserRole.MANAGER)
        actor = make_user(role=UserRole.MANAGER, name="Bob")
        asset = _make_asset(db_session)
        record_asset_action(
            db_session,
            asset=asset,
            actor=actor,
            action=AssetAction.DISPOSE,
            from_status=AssetStatus.IN_STOCK,
            to_status=AssetStatus.DISPOSED,
        )
        actor.deleted_at = datetime.now(UTC)
        db_session.commit()

        response = client.get(
            f"/api/v1/assets/{asset.id}/history",
            headers=auth_headers(manager),
        )
        assert response.status_code == 200
        events = response.json()["data"]
        assert len(events) == 1
        assert events[0]["actor"] is None


class TestAtomicityOnHistoryFailure:
    """If the audit-log write fails, the FSM transition must roll back too —
    the whole point of writing the history row inside the same transaction."""

    def test_assign_rolls_back_when_history_insert_fails(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session)
        starting_version = asset.version

        def _boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("simulated audit-log failure")

        # Patch where it's used (the endpoint module), not where it's defined.
        monkeypatch.setattr(
            "app.api.v1.endpoints.assets.record_asset_action",
            _boom,
        )

        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={"responsible_person_id": holder.id, "version": starting_version},
            headers=auth_headers(manager),
        )
        assert response.status_code >= 500

        db_session.expire_all()
        refreshed = db_session.get(Asset, asset.id)
        assert refreshed is not None
        assert refreshed.status is AssetStatus.IN_STOCK
        assert refreshed.responsible_person_id is None
        assert refreshed.version == starting_version
        assert _history_for(db_session, asset.id) == []
