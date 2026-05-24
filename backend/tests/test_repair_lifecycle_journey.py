"""End-to-end journey tests for the repair-request lifecycle.

Each test in this module walks a *complete* user story through the public
HTTP API — multiple requests in sequence, where each response's payload
(ids, ``version`` tokens, returned status) feeds into the next call.

Compare with ``test_repair_requests.py``, where each test focuses on a
single transition in isolation. The aim here is to prove that the FSM
defined in ``docs/system-design/11-asset-fsm.md`` holds together across
realistic flows — including the optimistic-lock ``version`` hand-off
between steps, which is invisible in single-transition tests because the
state is freshly built by ``_make_repair_request(...)``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole

_PURCHASE_DATE = date(2026, 1, 1)
_REPAIR_DATE = date(2026, 4, 20)

_COMPLETION_PAYLOAD = {
    "repair_date": _REPAIR_DATE.isoformat(),
    "fault_content": "GPU connector loose.",
    "repair_plan": "Replaced GPU ribbon cable.",
    "repair_cost": "3500.00",
    "repair_vendor": "Apple Authorized Service",
}


def _seed_assigned_asset(session: Session, holder: User) -> Asset:
    """Set the initial state: an asset that already lives with the holder.

    The journey itself starts at "holder reports a fault", so registration
    and assignment of the asset are background — they have their own
    coverage in test_assets.py.
    """
    asset = Asset(
        asset_code="AST-2026-00001",
        name="Business Laptop",
        model="Dell Latitude 7440",
        category="computer",
        supplier="Dell",
        purchase_date=_PURCHASE_DATE,
        purchase_amount=Decimal("1500.00"),
        location="Taipei HQ",
        department="IT",
        status=AssetStatus.IN_USE,
        responsible_person_id=holder.id,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


class TestRepairLifecycleJourney:
    """Multi-step journeys covering the full repair workflow over HTTP."""

    def test_submit_approve_complete_happy_path(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Holder reports → Manager approves → Manager completes.

        Verifies that:
        - each transition returns the new row ``version`` so the next call can
          present a fresh optimistic-lock token, and
        - the asset's status moves in lockstep with the repair request through
          the FSM: in_use → pending_repair → under_repair → in_use.
        """
        holder = make_user(role=UserRole.HOLDER)
        manager = make_user(role=UserRole.MANAGER, name="Manager")
        asset = _seed_assigned_asset(db_session, holder)
        asset_version_before_submit = asset.version

        # 1. Holder submits the repair request.
        submit_response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "Screen flickers when connected to HDMI.",
                "version": asset.version,
            },
            headers=auth_headers(holder),
        )
        assert submit_response.status_code == 201
        submitted = submit_response.json()["data"]
        repair_request_id = submitted["id"]
        assert submitted["status"] == "pending_review"
        assert submitted["version"] == 1  # newly-created row starts at 1

        # Asset must transition AND advance its version. A bug that wrote
        # status without bumping version would defeat optimistic locking
        # on any subsequent /unassign call — silent until the next race.
        db_session.refresh(asset)
        assert asset.status == AssetStatus.PENDING_REPAIR
        assert asset.version == asset_version_before_submit + 1

        # 2. Manager approves; both rows transition together.
        approve_response = client.post(
            f"/api/v1/repair-requests/{repair_request_id}/approve",
            json={"version": submitted["version"]},
            headers=auth_headers(manager),
        )
        assert approve_response.status_code == 200
        approved = approve_response.json()["data"]
        assert approved["status"] == "under_repair"
        assert approved["reviewer"] == {"id": manager.id, "name": "Manager"}
        # Optimistic-lock token must advance by exactly one. A bug that
        # forgot to bump it on UPDATE would silently break every subsequent
        # call that threads the version forward (e.g. /complete).
        assert approved["version"] == submitted["version"] + 1

        # Mid-flow integrity: approve must NOT touch responsible_person_id.
        # A bug that overwrote it with reviewer_id (easy mistake) would
        # still pass the status check above but orphan the asset's owner.
        # cast widens past mypy's narrowing from the earlier == PENDING_REPAIR
        # assertion; db_session.refresh() mutates in place so mypy cannot
        # know the literal has changed.
        db_session.refresh(asset)
        assert cast(AssetStatus, asset.status) == AssetStatus.UNDER_REPAIR
        assert asset.responsible_person_id == holder.id

        # 3. Manager completes the repair with the full report.
        complete_response = client.post(
            f"/api/v1/repair-requests/{repair_request_id}/complete",
            json={**_COMPLETION_PAYLOAD, "version": approved["version"]},
            headers=auth_headers(manager),
        )
        assert complete_response.status_code == 200
        completed = complete_response.json()["data"]
        assert completed["status"] == "completed"
        assert completed["completed_at"] is not None
        assert completed["repair_cost"] == "3500.00"
        assert completed["version"] == approved["version"] + 1

        db_session.refresh(asset)
        assert cast(AssetStatus, asset.status) == AssetStatus.IN_USE
        assert asset.responsible_person_id == holder.id

    def test_submit_then_reject_returns_asset_to_in_use(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Reject branch: asset must roll back to in_use, not stay pending."""
        holder = make_user(role=UserRole.HOLDER)
        manager = make_user(role=UserRole.MANAGER)
        asset = _seed_assigned_asset(db_session, holder)

        submit_response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "Could not reproduce on retest.",
                "version": asset.version,
            },
            headers=auth_headers(holder),
        )
        assert submit_response.status_code == 201
        submitted = submit_response.json()["data"]

        rejection_reason = "Issue could not be reproduced on retest."
        reject_response = client.post(
            f"/api/v1/repair-requests/{submitted['id']}/reject",
            json={
                "rejection_reason": rejection_reason,
                "version": submitted["version"],
            },
            headers=auth_headers(manager),
        )
        assert reject_response.status_code == 200
        rejected = reject_response.json()["data"]
        assert rejected["status"] == "rejected"
        # The rejection_reason is what the holder will see in the UI — a
        # bug that silently dropped it (e.g. wrong field name in the
        # endpoint's mapping) would still return 200 + status="rejected"
        # and leave the holder with no explanation.
        assert rejected["rejection_reason"] == rejection_reason

        db_session.refresh(asset)
        assert asset.status == AssetStatus.IN_USE

        # DB-side cross-check on the persisted column.
        persisted = db_session.get(RepairRequest, submitted["id"])
        assert persisted is not None
        assert persisted.rejection_reason == rejection_reason

    def test_approve_amend_details_then_complete_persists_all_fields(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Manager iterates on repair_details before issuing complete.

        Realistic flow: technician posts an interim diagnosis (PATCH
        /repair-details), corrects it once more, then files the final report
        via /complete. Each PATCH must advance the row ``version`` — a stale
        token from the previous PATCH must not be accepted on /complete.
        """
        holder = make_user(role=UserRole.HOLDER)
        manager = make_user(role=UserRole.MANAGER)
        asset = _seed_assigned_asset(db_session, holder)

        submit = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "GPU fan rattles under load.",
                "version": asset.version,
            },
            headers=auth_headers(holder),
        ).json()["data"]

        approved = client.post(
            f"/api/v1/repair-requests/{submit['id']}/approve",
            json={"version": submit["version"]},
            headers=auth_headers(manager),
        ).json()["data"]

        # First diagnosis — partial information.
        first_patch = client.patch(
            f"/api/v1/repair-requests/{submit['id']}/repair-details",
            json={
                "fault_content": "Initial guess: thermal paste.",
                "version": approved["version"],
            },
            headers=auth_headers(manager),
        )
        assert first_patch.status_code == 200
        first_patched = first_patch.json()["data"]
        assert first_patched["status"] == "under_repair"
        assert first_patched["fault_content"] == "Initial guess: thermal paste."
        assert first_patched["version"] == approved["version"] + 1

        # Second diagnosis — refines the first; passing the stale version
        # would be a real bug, so we use the new one.
        second_patch = client.patch(
            f"/api/v1/repair-requests/{submit['id']}/repair-details",
            json={
                "fault_content": "Actual cause: GPU fan bearing wear.",
                "repair_plan": "Replace GPU fan assembly.",
                "version": first_patched["version"],
            },
            headers=auth_headers(manager),
        )
        assert second_patch.status_code == 200
        second_patched = second_patch.json()["data"]
        assert second_patched["repair_plan"] == "Replace GPU fan assembly."

        # Stale token from the first PATCH must now be rejected.
        stale_response = client.post(
            f"/api/v1/repair-requests/{submit['id']}/complete",
            json={**_COMPLETION_PAYLOAD, "version": first_patched["version"]},
            headers=auth_headers(manager),
        )
        assert stale_response.status_code == 409

        # Fresh version on /complete succeeds and persists the final fields.
        complete = client.post(
            f"/api/v1/repair-requests/{submit['id']}/complete",
            json={**_COMPLETION_PAYLOAD, "version": second_patched["version"]},
            headers=auth_headers(manager),
        )
        assert complete.status_code == 200
        completed = complete.json()["data"]
        assert completed["status"] == "completed"
        assert completed["fault_content"] == _COMPLETION_PAYLOAD["fault_content"]
        assert completed["repair_plan"] == _COMPLETION_PAYLOAD["repair_plan"]
        assert completed["repair_cost"] == _COMPLETION_PAYLOAD["repair_cost"]
        assert completed["repair_vendor"] == _COMPLETION_PAYLOAD["repair_vendor"]

    def test_concurrent_managers_only_one_approval_wins(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Two managers race to approve the same request — only one wins.

        Both managers pull the request while it's still ``pending_review``
        and see ``version = 1``. They each post /approve with that version.
        Optimistic locking must let exactly one through (200) and reject
        the other (409 stale_version). The persisted ``reviewer_id`` must
        belong to the winner, not silently get overwritten by the loser.

        This is the protection that makes "two managers eyeballing the
        same queue at the same time" safe in production. Without it, the
        second approve would overwrite the first one's reviewer audit
        trail and possibly the timestamps.
        """
        holder = make_user(role=UserRole.HOLDER)
        manager_a = make_user(role=UserRole.MANAGER, name="Manager A")
        manager_b = make_user(role=UserRole.MANAGER, name="Manager B")
        asset = _seed_assigned_asset(db_session, holder)

        submitted = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "Fan loud under load.",
                "version": asset.version,
            },
            headers=auth_headers(holder),
        ).json()["data"]
        rr_id = submitted["id"]
        original_version = submitted["version"]

        # Both managers fetched the request while pending_review — they
        # have the same `version` token. We do not call GET twice here
        # because the version we care about is the one they would have
        # captured at the same moment; using ``original_version`` for both
        # POSTs is the strongest form of the race.
        approve_a = client.post(
            f"/api/v1/repair-requests/{rr_id}/approve",
            json={"version": original_version},
            headers=auth_headers(manager_a),
        )
        approve_b = client.post(
            f"/api/v1/repair-requests/{rr_id}/approve",
            json={"version": original_version},
            headers=auth_headers(manager_b),
        )

        # Exactly one must succeed.
        statuses = sorted([approve_a.status_code, approve_b.status_code])
        assert statuses == [200, 409], (
            f"Expected one approve to win (200) and one to lose (409); "
            f"got A={approve_a.status_code}, B={approve_b.status_code}"
        )

        # The loser must use the project's conflict envelope (see api-design
        # §6) so the frontend can show the "someone else already approved
        # this — refresh to see the latest state" message. A raw 500 here
        # would leave the user staring at a generic error.
        loser = approve_a if approve_a.status_code == 409 else approve_b
        assert loser.json()["error"]["code"] == "conflict"

        # Persisted reviewer_id must belong to the winner. A bug where the
        # losing transaction's write still landed (e.g. missing WHERE
        # version=X clause) would silently overwrite the audit trail.
        winner_id = manager_a.id if approve_a.status_code == 200 else manager_b.id
        persisted = db_session.get(RepairRequest, rr_id)
        assert persisted is not None
        assert persisted.reviewer_id == winner_id
        assert persisted.status == RepairRequestStatus.UNDER_REPAIR

    def test_holder_cannot_short_circuit_manager_steps_with_own_token(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Holder submits, then tries to drive the manager-only steps themselves.

        Demonstrates that RBAC is enforced **at every step**, not just at
        the entry point. A bug where ``require_manager`` only ran on /approve
        but not on /complete (or vice versa) would let a holder push the
        request through the FSM unilaterally. We poke all three manager-only
        endpoints with the holder's token and verify the request stays in
        ``pending_review`` afterwards.
        """
        holder = make_user(role=UserRole.HOLDER)
        manager = make_user(role=UserRole.MANAGER)
        asset = _seed_assigned_asset(db_session, holder)
        holder_auth = auth_headers(holder)

        submitted = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "Touchpad unresponsive.",
                "version": asset.version,
            },
            headers=holder_auth,
        ).json()["data"]
        rr_id = submitted["id"]
        version = submitted["version"]

        # All three manager-only verbs must reject the holder's token.
        approve_attempt = client.post(
            f"/api/v1/repair-requests/{rr_id}/approve",
            json={"version": version},
            headers=holder_auth,
        )
        assert approve_attempt.status_code == 403

        reject_attempt = client.post(
            f"/api/v1/repair-requests/{rr_id}/reject",
            json={"rejection_reason": "Self-reject.", "version": version},
            headers=holder_auth,
        )
        assert reject_attempt.status_code == 403

        complete_attempt = client.post(
            f"/api/v1/repair-requests/{rr_id}/complete",
            json={**_COMPLETION_PAYLOAD, "version": version},
            headers=holder_auth,
        )
        assert complete_attempt.status_code == 403

        # Critical part of this journey: zero of the rejected calls may
        # have leaked any state change. A bug where 403 was returned AFTER
        # the row had already been mutated would silently let the holder
        # advance the FSM and only the error envelope would hide it.
        persisted = db_session.get(RepairRequest, rr_id)
        assert persisted is not None
        assert persisted.status == RepairRequestStatus.PENDING_REVIEW
        assert persisted.reviewer_id is None
        assert persisted.version == version

        # The "real" manager can still drive it forward — proving the row
        # was not corrupted by the failed attempts.
        approved = client.post(
            f"/api/v1/repair-requests/{rr_id}/approve",
            json={"version": version},
            headers=auth_headers(manager),
        )
        assert approved.status_code == 200

    def test_holder_cannot_submit_repair_for_someone_elses_asset(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Cross-holder RBAC scoping on the submit endpoint.

        At the time of writing, no other test covers
        ``app/api/v1/endpoints/repair_requests.py`` line 902-903 — the
        check that the requester is the asset's ``responsible_person``.
        Without this guard, any holder could open repair tickets against
        any other holder's hardware and trigger a status change on a row
        they have no claim to.

        The journey: Holder B submits a repair targeting Holder A's
        asset, gets 403, and Holder A's asset is left untouched.
        """
        owner = make_user(role=UserRole.HOLDER, name="Owner")
        intruder = make_user(role=UserRole.HOLDER, name="Intruder")
        asset = _seed_assigned_asset(db_session, owner)
        asset_version_before = asset.version

        response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "Pretending it's mine.",
                "version": asset.version,
            },
            headers=auth_headers(intruder),
        )
        assert response.status_code == 403

        # Asset must be untouched — no status flip, no version bump, no
        # responsible_person rewrite. A bug that fired the FSM transition
        # before checking ownership would corrupt the owner's asset row.
        db_session.refresh(asset)
        assert asset.status == AssetStatus.IN_USE
        assert asset.responsible_person_id == owner.id
        assert asset.version == asset_version_before

        # No repair_request row should have been written.
        leaked = db_session.scalar(
            select(RepairRequest).where(RepairRequest.asset_id == asset.id)
        )
        assert leaked is None

    def test_holder_can_track_request_status_through_each_state(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Holder's read endpoint reflects the same status the manager sees.

        Important for the UI: between each manager action, the holder reloads
        the page (GET /repair-requests/{id}) and must see the new state. A
        stale read here would silently give the holder a wrong view.
        """
        holder = make_user(role=UserRole.HOLDER)
        manager = make_user(role=UserRole.MANAGER)
        asset = _seed_assigned_asset(db_session, holder)
        holder_auth = auth_headers(holder)
        manager_auth = auth_headers(manager)

        submitted = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset.id,
                "fault_description": "Keyboard occasionally drops keystrokes.",
                "version": asset.version,
            },
            headers=holder_auth,
        ).json()["data"]
        rr_id = submitted["id"]

        # Right after submit, holder sees pending_review.
        after_submit = client.get(f"/api/v1/repair-requests/{rr_id}", headers=holder_auth)
        assert after_submit.json()["data"]["status"] == "pending_review"

        # After approve, holder's view advances to under_repair without
        # needing any client-side state update.
        approved = client.post(
            f"/api/v1/repair-requests/{rr_id}/approve",
            json={"version": submitted["version"]},
            headers=manager_auth,
        ).json()["data"]
        after_approve = client.get(f"/api/v1/repair-requests/{rr_id}", headers=holder_auth)
        assert after_approve.json()["data"]["status"] == "under_repair"

        # After complete, status reaches its terminal state and completed_at
        # is populated.
        completed = client.post(
            f"/api/v1/repair-requests/{rr_id}/complete",
            json={**_COMPLETION_PAYLOAD, "version": approved["version"]},
            headers=manager_auth,
        ).json()["data"]
        after_complete = client.get(f"/api/v1/repair-requests/{rr_id}", headers=holder_auth)
        final_data = after_complete.json()["data"]
        assert final_data["status"] == "completed"
        assert final_data["completed_at"] == completed["completed_at"]

        # Final DB cross-check: the persisted enum value matches the API view.
        # No expire_all() needed — the session's default expire_on_commit
        # means attributes are already fresh on the next read.
        persisted = db_session.get(RepairRequest, rr_id)
        assert persisted is not None
        assert persisted.status == RepairRequestStatus.COMPLETED
