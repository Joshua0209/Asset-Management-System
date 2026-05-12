from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.repair_requests import _next_repair_id
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
        repair_id=_next_repair_id(session),
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
        db_session.begin()

        before = len(_history_for(db_session, asset.id))

        # Returns None — the audit row is added to the session via db.add
        # but not surfaced to the caller (forces all reads through the model
        # query, not a service-returned reference).
        result = record_asset_action(
            db_session,
            asset=asset,
            actor=actor,
            action=AssetAction.DISPOSE,
            from_status=AssetStatus.IN_STOCK,
            to_status=AssetStatus.DISPOSED,
            metadata={"disposal_reason": "End of life"},
        )
        assert result is None

        # Pending state visible only inside this transaction.
        db_session.flush()
        in_session = _history_for(db_session, asset.id)
        assert len(in_session) == before + 1
        latest = in_session[-1]
        assert latest.action is AssetAction.DISPOSE
        assert latest.event_metadata == {"disposal_reason": "End of life"}

    def test_record_asset_action_requires_open_transaction(
        self, db_session: Session
    ) -> None:
        # Atomicity guard: without an open txn the row would auto-commit alone,
        # defeating the "no transition without log" invariant.
        asset = _make_asset(db_session)
        actor = User(
            email="m@example.com",
            password_hash="x",
            name="M",
            role=UserRole.MANAGER,
            department="IT",
        )
        db_session.add(actor)
        db_session.commit()  # Closes the implicit transaction.

        with pytest.raises(RuntimeError, match="open transaction"):
            record_asset_action(
                db_session,
                asset=asset,
                actor=actor,
                action=AssetAction.DISPOSE,
                from_status=AssetStatus.IN_STOCK,
                to_status=AssetStatus.DISPOSED,
            )

    def test_record_asset_action_rejects_non_json_metadata(
        self, db_session: Session
    ) -> None:
        # Surfaces non-encodable values as TypeError at the call site
        # rather than as a generic flush-time error later.
        asset = _make_asset(db_session)
        actor = User(
            email="m2@example.com",
            password_hash="x",
            name="M2",
            role=UserRole.MANAGER,
            department="IT",
        )
        db_session.add(actor)
        db_session.commit()
        db_session.begin()

        with pytest.raises(TypeError, match="JSON-serializable"):
            record_asset_action(
                db_session,
                asset=asset,
                actor=actor,
                action=AssetAction.DISPOSE,
                from_status=AssetStatus.IN_STOCK,
                to_status=AssetStatus.DISPOSED,
                metadata={"when": datetime.now(UTC)},
            )


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
            json={
                "responsible_person_id": holder.id,
                "version": asset.version,
                "assignment_date": "2026-05-01",
            },
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
            json={
                "reason": "End of project",
                "version": asset.version,
                "unassignment_date": "2026-05-06",
            },
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
            json={
                "responsible_person_id": holder.id,
                "version": asset.version,
                "assignment_date": "2026-05-01",
            },
            headers=auth_headers(manager),
        )
        db_session.refresh(asset)
        client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            json={
                "reason": "Returned",
                "version": asset.version,
                "unassignment_date": "2026-05-06",
            },
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
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.db.session import get_db
        from app.main import app

        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session)
        starting_version = asset.version

        def _boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("simulated audit-log failure")

        # Patch where the symbol is *used* (the endpoint module), not where
        # it is defined.
        monkeypatch.setattr(
            "app.api.v1.endpoints.assets.record_asset_action",
            _boom,
        )

        # Build a client that surfaces server errors as 500 instead of
        # re-raising them into the test — matches the production path where
        # Starlette converts unhandled exceptions to a 500 response.
        def _override_get_db() -> object:
            yield db_session

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app, raise_server_exceptions=False) as test_client:
                response = test_client.post(
                    f"/api/v1/assets/{asset.id}/assign",
                    json={
                        "responsible_person_id": holder.id,
                        "version": starting_version,
                        "assignment_date": "2026-05-01",
                    },
                    headers=auth_headers(manager),
                )
        finally:
            app.dependency_overrides.clear()
        assert response.status_code >= 500

        db_session.expire_all()
        refreshed = db_session.get(Asset, asset.id)
        assert refreshed is not None
        # The whole FSM transition is rolled back — status/holder/version
        # all match the pre-call state, and no history row was persisted.
        assert refreshed.status is AssetStatus.IN_STOCK
        assert refreshed.responsible_person_id is None
        assert refreshed.version == starting_version
        assert _history_for(db_session, asset.id) == []

    @staticmethod
    def _drive_failure(
        db_session: Session,
        endpoint_module: str,
        request_method: str,
        url: str,
        json_payload: dict[str, Any],
        actor_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> int:
        """Boilerplate: monkey-patch ``record_asset_action`` in the named
        endpoint module to raise, drive the request, and return the status."""
        from app.db.session import get_db
        from app.main import app

        def _boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("simulated audit-log failure")

        monkeypatch.setattr(f"{endpoint_module}.record_asset_action", _boom)

        def _override_get_db() -> object:
            yield db_session

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app, raise_server_exceptions=False) as test_client:
                response = test_client.request(
                    request_method,
                    url,
                    json=json_payload,
                    headers=actor_headers,
                )
        finally:
            app.dependency_overrides.clear()
        return response.status_code

    def test_approve_rolls_back_when_history_insert_fails(
        self,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.PENDING_REPAIR,
            responsible_person_id=holder.id,
        )
        rr = _make_repair_request(db_session, asset=asset, requester=holder)
        starting_rr_version = rr.version
        starting_asset_version = asset.version

        status_code = self._drive_failure(
            db_session,
            "app.api.v1.endpoints.repair_requests",
            "POST",
            f"/api/v1/repair-requests/{rr.id}/approve",
            {"version": starting_rr_version},
            auth_headers(manager),
            monkeypatch,
        )
        assert status_code >= 500

        db_session.expire_all()
        refreshed_asset = db_session.get(Asset, asset.id)
        refreshed_rr = db_session.get(RepairRequest, rr.id)
        assert refreshed_asset is not None
        assert refreshed_rr is not None
        # FSM rolled back across both the asset and the repair request, no
        # history row landed — proves _commit_repair_change atomicity.
        assert refreshed_asset.status is AssetStatus.PENDING_REPAIR
        assert refreshed_asset.version == starting_asset_version
        assert refreshed_rr.status is RepairRequestStatus.PENDING_REVIEW
        assert refreshed_rr.version == starting_rr_version
        assert _history_for(db_session, asset.id) == []

    def test_reject_rolls_back_when_history_insert_fails(
        self,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.PENDING_REPAIR,
            responsible_person_id=holder.id,
        )
        rr = _make_repair_request(db_session, asset=asset, requester=holder)
        starting_rr_version = rr.version

        status_code = self._drive_failure(
            db_session,
            "app.api.v1.endpoints.repair_requests",
            "POST",
            f"/api/v1/repair-requests/{rr.id}/reject",
            {"version": starting_rr_version, "rejection_reason": "Out of scope."},
            auth_headers(manager),
            monkeypatch,
        )
        assert status_code >= 500

        db_session.expire_all()
        refreshed_asset = db_session.get(Asset, asset.id)
        refreshed_rr = db_session.get(RepairRequest, rr.id)
        assert refreshed_asset is not None
        assert refreshed_rr is not None
        assert refreshed_asset.status is AssetStatus.PENDING_REPAIR
        assert refreshed_rr.status is RepairRequestStatus.PENDING_REVIEW
        assert refreshed_rr.rejection_reason is None
        assert _history_for(db_session, asset.id) == []

    def test_complete_rolls_back_when_history_insert_fails(
        self,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        monkeypatch: pytest.MonkeyPatch,
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

        status_code = self._drive_failure(
            db_session,
            "app.api.v1.endpoints.repair_requests",
            "POST",
            f"/api/v1/repair-requests/{rr.id}/complete",
            {
                "version": rr.version,
                "repair_date": _REPAIR_DATE.isoformat(),
                "fault_content": "Fan failure",
                "repair_plan": "Replaced fan",
                "repair_cost": "1234.56",
                "repair_vendor": "Acme Repair",
            },
            auth_headers(manager),
            monkeypatch,
        )
        assert status_code >= 500

        db_session.expire_all()
        refreshed_asset = db_session.get(Asset, asset.id)
        refreshed_rr = db_session.get(RepairRequest, rr.id)
        assert refreshed_asset is not None
        assert refreshed_rr is not None
        assert refreshed_asset.status is AssetStatus.UNDER_REPAIR
        assert refreshed_rr.status is RepairRequestStatus.UNDER_REPAIR
        assert refreshed_rr.completed_at is None
        assert _history_for(db_session, asset.id) == []

    def test_submit_repair_rolls_back_when_history_insert_fails(
        self,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # submit_repair has a different flow than the _commit_repair_change
        # endpoints (manual db.flush between PK-assign and image rows, plus
        # finally-cleanup), so it gets its own dedicated atomicity test.
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(
            db_session,
            status=AssetStatus.IN_USE,
            responsible_person_id=holder.id,
        )
        starting_version = asset.version

        status_code = self._drive_failure(
            db_session,
            "app.api.v1.endpoints.repair_requests",
            "POST",
            "/api/v1/repair-requests",
            {
                "asset_id": asset.id,
                "fault_description": "Won't power on.",
                "version": starting_version,
            },
            auth_headers(holder),
            monkeypatch,
        )
        assert status_code >= 500

        db_session.expire_all()
        refreshed = db_session.get(Asset, asset.id)
        assert refreshed is not None
        # No half-committed RepairRequest row, no history row, asset stays IN_USE.
        assert refreshed.status is AssetStatus.IN_USE
        assert refreshed.version == starting_version
        assert _history_for(db_session, asset.id) == []
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(RepairRequest)
                .where(RepairRequest.asset_id == asset.id)
            )
            == 0
        )


class TestRelationshipInvariants:
    """The 'no transition without log' invariant depends on
    ``Asset.action_histories`` being read-only — direct
    ``asset.action_histories.append(...)`` writes must NOT persist."""

    def test_action_histories_relationship_is_viewonly(self) -> None:
        from sqlalchemy import inspect as sa_inspect

        rel = sa_inspect(Asset).relationships["action_histories"]
        assert rel.viewonly is True

    def test_appending_via_viewonly_relationship_is_silently_ignored(
        self,
        db_session: Session,
        make_user: Callable[..., User],
    ) -> None:
        # Documents the silent-by-design behavior so anyone debugging "why
        # is the history empty?" finds the test that explains it.
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)
        rogue = AssetActionHistory(
            asset_id=asset.id,
            actor_id=manager.id,
            action=AssetAction.DISPOSE,
            from_status=AssetStatus.IN_STOCK.value,
            to_status=AssetStatus.DISPOSED.value,
        )
        asset.action_histories.append(rogue)
        db_session.commit()
        db_session.expire_all()

        # The append did NOT persist. ALL writes must go through
        # record_asset_action.
        assert _history_for(db_session, asset.id) == []


class TestPaginationEdges:
    def test_empty_history_returns_zero_total(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)

        response = client.get(
            f"/api/v1/assets/{asset.id}/history",
            headers=auth_headers(manager),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []
        assert body["meta"]["total"] == 0

    def test_page_beyond_total_returns_empty_data_with_correct_meta(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)
        record_asset_action(
            db_session,
            asset=asset,
            actor=manager,
            action=AssetAction.DISPOSE,
            from_status=AssetStatus.IN_STOCK,
            to_status=AssetStatus.DISPOSED,
        )
        db_session.commit()

        response = client.get(
            f"/api/v1/assets/{asset.id}/history?page=99&per_page=20",
            headers=auth_headers(manager),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []
        assert body["meta"]["total"] == 1
        assert body["meta"]["page"] == 99

    def test_per_page_over_max_returns_422(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)
        response = client.get(
            f"/api/v1/assets/{asset.id}/history?per_page=101",
            headers=auth_headers(manager),
        )
        assert response.status_code == 422

    def test_page_zero_returns_422(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)
        response = client.get(
            f"/api/v1/assets/{asset.id}/history?page=0",
            headers=auth_headers(manager),
        )
        assert response.status_code == 422


class TestSchemaAliasing:
    def test_validation_alias_accepts_event_metadata_attr_name(self) -> None:
        # Round-trip via from_attributes: ORM attr name `event_metadata`
        # populates the wire field aliased as `metadata`. The payload must
        # match the DISPOSE variant of the discriminated union — the alias
        # plumbing is what's under test here, not the shape validation.
        from app.schemas.asset import AssetActionHistoryRead, DisposeMetadata

        history = AssetActionHistory(
            id="h1",
            asset_id="a1",
            actor_id=None,
            action=AssetAction.DISPOSE,
            from_status="in_stock",
            to_status="disposed",
            event_metadata={"disposal_reason": "End of life"},
            created_at=datetime.now(UTC),
        )
        schema = AssetActionHistoryRead.model_validate(history)
        assert isinstance(schema.metadata, DisposeMetadata)
        assert schema.metadata.disposal_reason == "End of life"
        # Wire-format uses the serialization alias.
        dumped = schema.model_dump(by_alias=True)
        assert "metadata" in dumped
        assert "event_metadata" not in dumped


class TestMetadataDiscriminatedUnion:
    """Each AssetAction has a per-action metadata schema; the union is
    discriminated by the sibling `action` field. Mismatched shapes raise
    ValidationError at the schema boundary, so a typo in a future writer
    (or a renamed field that didn't propagate to the schema) is caught
    statically rather than silently rendered as `Record<string, any>`."""

    def _build_history(
        self, action: AssetAction, metadata: dict[str, Any] | None
    ) -> AssetActionHistory:
        return AssetActionHistory(
            id="h1",
            asset_id="a1",
            actor_id=None,
            action=action,
            from_status="in_stock",
            to_status="in_use",
            event_metadata=metadata,
            created_at=datetime.now(UTC),
        )

    def test_assign_payload_validates(self) -> None:
        from app.schemas.asset import AssetActionHistoryRead, AssignMetadata

        actor_id = "11111111-1111-1111-1111-111111111111"
        history = self._build_history(
            AssetAction.ASSIGN,
            {
                "responsible_person_id": actor_id,
                "responsible_person_name": "Alice",
            },
        )
        schema = AssetActionHistoryRead.model_validate(history)
        assert isinstance(schema.metadata, AssignMetadata)
        assert schema.metadata.responsible_person_id == actor_id
        assert schema.metadata.responsible_person_name == "Alice"

    def test_unassign_payload_validates(self) -> None:
        from app.schemas.asset import AssetActionHistoryRead, UnassignMetadata

        prev_id = "22222222-2222-2222-2222-222222222222"
        history = self._build_history(
            AssetAction.UNASSIGN,
            {"reason": "Returned", "previous_responsible_person_id": prev_id},
        )
        schema = AssetActionHistoryRead.model_validate(history)
        assert isinstance(schema.metadata, UnassignMetadata)
        assert schema.metadata.reason == "Returned"
        assert schema.metadata.previous_responsible_person_id == prev_id

    def test_dispose_payload_validates(self) -> None:
        from app.schemas.asset import AssetActionHistoryRead, DisposeMetadata

        history = self._build_history(
            AssetAction.DISPOSE, {"disposal_reason": "Damaged"}
        )
        schema = AssetActionHistoryRead.model_validate(history)
        assert isinstance(schema.metadata, DisposeMetadata)
        assert schema.metadata.disposal_reason == "Damaged"

    def test_submit_repair_payload_validates(self) -> None:
        from app.schemas.asset import AssetActionHistoryRead, SubmitRepairMetadata

        rr_id = "33333333-3333-3333-3333-333333333333"
        history = self._build_history(
            AssetAction.SUBMIT_REPAIR,
            {"repair_request_id": rr_id, "fault_description": "Cracked screen"},
        )
        schema = AssetActionHistoryRead.model_validate(history)
        assert isinstance(schema.metadata, SubmitRepairMetadata)
        assert schema.metadata.repair_request_id == rr_id
        assert schema.metadata.fault_description == "Cracked screen"

    def test_approve_repair_payload_validates(self) -> None:
        from app.schemas.asset import (
            ApproveRepairMetadata,
            AssetActionHistoryRead,
        )

        rr_id = "44444444-4444-4444-4444-444444444444"
        history = self._build_history(
            AssetAction.APPROVE_REPAIR, {"repair_request_id": rr_id}
        )
        schema = AssetActionHistoryRead.model_validate(history)
        assert isinstance(schema.metadata, ApproveRepairMetadata)
        assert schema.metadata.repair_request_id == rr_id

    def test_reject_repair_payload_validates(self) -> None:
        from app.schemas.asset import AssetActionHistoryRead, RejectRepairMetadata

        rr_id = "55555555-5555-5555-5555-555555555555"
        history = self._build_history(
            AssetAction.REJECT_REPAIR,
            {"repair_request_id": rr_id, "rejection_reason": "Out of scope"},
        )
        schema = AssetActionHistoryRead.model_validate(history)
        assert isinstance(schema.metadata, RejectRepairMetadata)
        assert schema.metadata.repair_request_id == rr_id
        assert schema.metadata.rejection_reason == "Out of scope"

    def test_complete_repair_payload_validates(self) -> None:
        from app.schemas.asset import (
            AssetActionHistoryRead,
            CompleteRepairMetadata,
        )

        rr_id = "66666666-6666-6666-6666-666666666666"
        history = self._build_history(
            AssetAction.COMPLETE_REPAIR,
            {
                "repair_request_id": rr_id,
                "repair_cost": "1234.56",
                "repair_vendor": "Acme",
            },
        )
        schema = AssetActionHistoryRead.model_validate(history)
        assert isinstance(schema.metadata, CompleteRepairMetadata)
        assert schema.metadata.repair_cost == "1234.56"
        assert schema.metadata.repair_vendor == "Acme"

    def test_mismatched_shape_raises_validation_error(self) -> None:
        # action=DISPOSE but the payload is an ASSIGN shape — the
        # discriminator drives validation against DisposeMetadata, which
        # rejects the wrong keys.
        from pydantic import ValidationError

        from app.schemas.asset import AssetActionHistoryRead

        history = self._build_history(
            AssetAction.DISPOSE,
            {"responsible_person_id": "x", "responsible_person_name": "y"},
        )
        with pytest.raises(ValidationError):
            AssetActionHistoryRead.model_validate(history)

    def test_missing_required_field_raises_validation_error(self) -> None:
        # ASSIGN requires both responsible_person_id and responsible_person_name.
        from pydantic import ValidationError

        from app.schemas.asset import AssetActionHistoryRead

        history = self._build_history(
            AssetAction.ASSIGN,
            {"responsible_person_id": "77777777-7777-7777-7777-777777777777"},
        )
        with pytest.raises(ValidationError):
            AssetActionHistoryRead.model_validate(history)

    def test_extra_field_raises_validation_error(self) -> None:
        # extra="forbid" — adding a field that didn't make it into the
        # schema should fail loudly, not silently drop.
        from pydantic import ValidationError

        from app.schemas.asset import AssetActionHistoryRead

        history = self._build_history(
            AssetAction.DISPOSE,
            {"disposal_reason": "ok", "stray_field": "should not be here"},
        )
        with pytest.raises(ValidationError):
            AssetActionHistoryRead.model_validate(history)

    def test_null_metadata_is_allowed(self) -> None:
        # Historic rows / future actions with no payload remain valid.
        from app.schemas.asset import AssetActionHistoryRead

        history = self._build_history(AssetAction.DISPOSE, None)
        schema = AssetActionHistoryRead.model_validate(history)
        assert schema.metadata is None


class TestMetadataOpenAPISchema:
    """Pydantic v2 emits `oneOf` + `discriminator` for tagged unions; this
    is what TypeScript generators consume to produce a real discriminated
    union on the client. If a future refactor flattens the union or drops
    the discriminator, the generated TS types regress to `Record<string,
    any>` — and that regression slips past `tsc --strict`."""

    def test_openapi_metadata_is_oneof_with_discriminator(self) -> None:
        from app.main import app

        spec = app.openapi()
        schemas = spec["components"]["schemas"]
        history_read = schemas["AssetActionHistoryRead"]
        metadata_prop = history_read["properties"]["metadata"]

        # `oneOf` lives behind the anyOf-with-null wrapper for `T | None`.
        union_node = (
            metadata_prop
            if "oneOf" in metadata_prop
            else next(
                (
                    branch
                    for branch in metadata_prop.get("anyOf", [])
                    if "oneOf" in branch
                ),
                None,
            )
        )
        assert union_node is not None, metadata_prop
        assert union_node.get("discriminator", {}).get("propertyName") == "action"
        # All seven AssetAction values must appear as discriminator mappings.
        mapping = union_node["discriminator"]["mapping"]
        expected = {a.value for a in AssetAction}
        assert set(mapping.keys()) == expected


class TestHistoryEndpoint503Path:
    def test_db_failure_returns_503_envelope(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Drives the SQLAlchemyError handler at line 433-443 of assets.py so
        # a future regression that breaks the 503 envelope (or removes
        # _safe_log) is caught in CI.
        from sqlalchemy.exc import OperationalError

        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)

        original_scalar = Session.scalar
        call_count = {"n": 0}

        def _flaky_scalar(self: Session, *args: object, **kwargs: object) -> object:
            call_count["n"] += 1
            # First scalar call is the asset-existence probe; let it pass.
            # The second is the count() in list_asset_history — make it die.
            if call_count["n"] == 2:
                raise OperationalError("SELECT count(*)", {}, Exception("boom"))
            return original_scalar(self, *args, **kwargs)

        monkeypatch.setattr(Session, "scalar", _flaky_scalar)

        response = client.get(
            f"/api/v1/assets/{asset.id}/history",
            headers=auth_headers(manager),
        )
        assert response.status_code == 503
        body = response.json()
        # Must use the project envelope, not raw FastAPI {"detail": ...}.
        assert "error" in body
        assert body["error"]["code"] == "service_unavailable"


class TestConcurrentAssign:
    def test_second_assign_after_version_drift_writes_no_extra_history(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Two managers race on the same asset using the same starting
        # version; optimistic locking must reject the second call AND no
        # extra history row should land — the audit row is conditional on
        # the FSM mutation succeeding.
        manager_a = make_user(role=UserRole.MANAGER, email="a@example.com")
        manager_b = make_user(role=UserRole.MANAGER, email="b@example.com")
        holder = make_user(role=UserRole.HOLDER)
        asset = _make_asset(db_session)
        starting_version = asset.version

        ok = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={
                "responsible_person_id": holder.id,
                "version": starting_version,
                "assignment_date": "2026-05-01",
            },
            headers=auth_headers(manager_a),
        )
        assert ok.status_code == 200

        conflict = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            json={
                "responsible_person_id": holder.id,
                "version": starting_version,
                "assignment_date": "2026-05-01",
            },
            headers=auth_headers(manager_b),
        )
        assert conflict.status_code == 409

        events = _history_for(db_session, asset.id)
        assert len(events) == 1
        assert events[0].actor_id == manager_a.id


class TestHardDeletedActor:
    def test_actor_id_null_renders_actor_as_null(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Distinct from the soft-deleted-actor case: ON DELETE SET NULL on
        # the FK can produce actor_id IS NULL via the DB layer too.
        manager = make_user(role=UserRole.MANAGER)
        asset = _make_asset(db_session)
        history = AssetActionHistory(
            asset_id=asset.id,
            actor_id=None,  # null at the FK level, not via soft-delete
            action=AssetAction.DISPOSE,
            from_status=AssetStatus.IN_STOCK.value,
            to_status=AssetStatus.DISPOSED.value,
        )
        db_session.add(history)
        db_session.commit()

        response = client.get(
            f"/api/v1/assets/{asset.id}/history",
            headers=auth_headers(manager),
        )
        assert response.status_code == 200
        events = response.json()["data"]
        assert len(events) == 1
        assert events[0]["actor"] is None
