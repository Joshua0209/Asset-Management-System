"""End-to-end journey tests for the asset lifecycle.

The asset FSM in ``docs/system-design/11-asset-fsm.md`` defines four states
(``in_stock``, ``in_use``, ``pending_repair``/``under_repair``, ``disposed``)
and the legal transitions between them. ``test_assets.py`` covers each
transition in isolation; this module strings them together into realistic
operator journeys, including the cross-resource lock where an active repair
request blocks ``unassign`` and ``dispose``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.user import User, UserRole

_REGISTER_PAYLOAD = {
    "name": "Business Laptop",
    "model": "Dell Latitude 7440",
    "category": "computer",
    "supplier": "Dell",
    "purchase_date": "2026-01-01",
    "purchase_amount": "1500.00",
    "location": "Taipei HQ",
    "department": "IT",
}
_ASSIGNMENT_DATE_ISO = "2026-04-15"
_UNASSIGNMENT_DATE_ISO = "2026-04-20"
_REPAIR_COMPLETION_PAYLOAD = {
    "repair_date": "2026-04-22",
    "fault_content": "Battery swelling.",
    "repair_plan": "Replaced battery module.",
    "repair_cost": "1200.00",
    "repair_vendor": "Dell Authorized Service",
}


def _register_and_assign_via_api(
    client: TestClient,
    manager_auth: dict[str, str],
    holder: User,
) -> dict[str, Any]:
    """Drive ``POST /assets`` then ``POST /assets/{id}/assign`` over HTTP.

    Used by journey tests whose *subject* starts after the asset is already
    in a holder's hands — registration and assignment are background here.
    The full register-to-dispose walk is covered inline in
    ``test_register_assign_unassign_dispose_full_lifecycle``.
    """
    register_response = client.post("/api/v1/assets", json=_REGISTER_PAYLOAD, headers=manager_auth)
    assert register_response.status_code == 201, register_response.text
    registered = register_response.json()["data"]
    assign_response = client.post(
        f"/api/v1/assets/{registered['id']}/assign",
        json={
            "responsible_person_id": holder.id,
            "assignment_date": _ASSIGNMENT_DATE_ISO,
            "version": registered["version"],
        },
        headers=manager_auth,
    )
    assert assign_response.status_code == 200, assign_response.text
    assigned: dict[str, Any] = assign_response.json()["data"]
    return assigned


class TestAssetLifecycleJourney:
    """Multi-step journeys covering the full asset FSM over HTTP."""

    def test_register_assign_unassign_dispose_full_lifecycle(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Walk the asset all the way from procurement to retirement.

        in_stock → in_use → in_stock → disposed.

        Each step must (1) succeed for a manager, (2) advance the row
        ``version``, and (3) be visible to the next step via the version
        returned in the response — not refetched from the DB.
        """
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER, name="Alice")
        manager_auth = auth_headers(manager)

        # 1. Register — manager creates a brand-new asset in stock.
        register_response = client.post(
            "/api/v1/assets", json=_REGISTER_PAYLOAD, headers=manager_auth
        )
        assert register_response.status_code == 201
        registered = register_response.json()["data"]
        asset_id = registered["id"]
        assert registered["status"] == "in_stock"
        assert registered["responsible_person_id"] is None

        # 2. Assign — manager hands the asset over to a holder.
        assign_response = client.post(
            f"/api/v1/assets/{asset_id}/assign",
            json={
                "responsible_person_id": holder.id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "version": registered["version"],
            },
            headers=manager_auth,
        )
        assert assign_response.status_code == 200
        assigned = assign_response.json()["data"]
        assert assigned["status"] == "in_use"
        assert assigned["responsible_person_id"] == holder.id
        assert assigned["version"] == registered["version"] + 1

        # 3. Unassign — employee leaves, asset returns to stock.
        unassign_response = client.post(
            f"/api/v1/assets/{asset_id}/unassign",
            json={
                "reason": "Employee transfer to another department.",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "version": assigned["version"],
            },
            headers=manager_auth,
        )
        assert unassign_response.status_code == 200
        unassigned = unassign_response.json()["data"]
        assert unassigned["status"] == "in_stock"
        assert unassigned["responsible_person_id"] is None

        # 4. Dispose — end-of-life. Terminal state, no further transitions.
        dispose_response = client.post(
            f"/api/v1/assets/{asset_id}/dispose",
            json={
                "disposal_reason": "End of life — exceeded warranty.",
                "version": unassigned["version"],
            },
            headers=manager_auth,
        )
        assert dispose_response.status_code == 200
        disposed = dispose_response.json()["data"]
        assert disposed["status"] == "disposed"

        # Sanity check from the DB side — the persisted enum matches.
        # No expire_all() needed; expire_on_commit (default True) already
        # refreshes attributes on the next read.
        persisted = db_session.get(Asset, asset_id)
        assert persisted is not None
        assert persisted.status == AssetStatus.DISPOSED

    def test_register_assign_unassign_reassign_to_different_holder(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """An asset can be reassigned to a different holder after unassignment.

        Common real-world flow: device returns to stock when an employee
        leaves, then ships to the next user. We verify the ``responsible_person``
        link is cleanly broken on unassign and re-established on the second
        assign — not stamped onto the wrong row.
        """
        manager = make_user(role=UserRole.MANAGER)
        first_holder = make_user(role=UserRole.HOLDER, name="Alice")
        second_holder = make_user(role=UserRole.HOLDER, name="Bob")
        manager_auth = auth_headers(manager)

        assigned_to_first = _register_and_assign_via_api(client, manager_auth, first_holder)
        asset_id = assigned_to_first["id"]
        assert assigned_to_first["responsible_person_id"] == first_holder.id

        unassign_response = client.post(
            f"/api/v1/assets/{asset_id}/unassign",
            json={
                "reason": "Alice left the company.",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "version": assigned_to_first["version"],
            },
            headers=manager_auth,
        )
        assert unassign_response.status_code == 200, unassign_response.text
        unassigned = unassign_response.json()["data"]
        assert unassigned["responsible_person_id"] is None

        assigned_to_second = client.post(
            f"/api/v1/assets/{asset_id}/assign",
            json={
                "responsible_person_id": second_holder.id,
                "assignment_date": _UNASSIGNMENT_DATE_ISO,
                "version": unassigned["version"],
            },
            headers=manager_auth,
        )
        assert assigned_to_second.status_code == 200
        second_data = assigned_to_second.json()["data"]
        assert second_data["status"] == "in_use"
        assert second_data["responsible_person_id"] == second_holder.id
        assert second_data["responsible_person"]["id"] == second_holder.id
        assert second_data["responsible_person"]["name"] == "Bob"

    def test_active_repair_blocks_unassign_until_completed(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Cross-resource lock: an in-flight repair request must block unassign.

        Operational reason: if the holder is removed from the asset while
        repair is in progress, the responsible_person link becomes
        inconsistent with the repair request that still names them. The API
        enforces this with a 409 — we walk the full path that unblocks it
        (approve → complete) and prove unassign then succeeds.
        """
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        manager_auth = auth_headers(manager)
        holder_auth = auth_headers(holder)

        # Setup: asset already registered and in the holder's hands.
        assigned = _register_and_assign_via_api(client, manager_auth, holder)
        asset_id = assigned["id"]

        # Holder reports a fault. Asset is now pending_repair (advancing its
        # version) and an active repair request exists.
        submit_response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset_id,
                "fault_description": "Battery does not charge.",
                "version": assigned["version"],
            },
            headers=holder_auth,
        )
        assert submit_response.status_code == 201, submit_response.text
        submitted = submit_response.json()["data"]
        rr_id = submitted["id"]

        # Manager tries to unassign while the repair is active — must fail.
        # We fetch the current asset version since /repair-requests bumped it.
        current_asset_response = client.get(f"/api/v1/assets/{asset_id}", headers=manager_auth)
        assert current_asset_response.status_code == 200, current_asset_response.text
        current_asset = current_asset_response.json()["data"]
        blocked_unassign = client.post(
            f"/api/v1/assets/{asset_id}/unassign",
            json={
                "reason": "Trying anyway.",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "version": current_asset["version"],
            },
            headers=manager_auth,
        )
        assert blocked_unassign.status_code == 409
        assert blocked_unassign.json()["error"]["code"] == "invalid_transition"

        # Verify the failed 409 did NOT mutate the asset. A bug that
        # executed the unassign but returned 409 by mistake (e.g. status
        # set after the commit, then accidentally overwritten by the
        # error path) would orphan the holder silently.
        unchanged_response = client.get(f"/api/v1/assets/{asset_id}", headers=manager_auth)
        assert unchanged_response.status_code == 200, unchanged_response.text
        unchanged_asset = unchanged_response.json()["data"]
        assert unchanged_asset["status"] == current_asset["status"]
        assert unchanged_asset["responsible_person_id"] == holder.id
        assert unchanged_asset["version"] == current_asset["version"]

        # Resolve the block: approve, then complete the repair request.
        approve_resp = client.post(
            f"/api/v1/repair-requests/{rr_id}/approve",
            json={"version": submitted["version"]},
            headers=manager_auth,
        )
        assert approve_resp.status_code == 200
        approved = approve_resp.json()["data"]
        complete_resp = client.post(
            f"/api/v1/repair-requests/{rr_id}/complete",
            json={**_REPAIR_COMPLETION_PAYLOAD, "version": approved["version"]},
            headers=manager_auth,
        )
        assert complete_resp.status_code == 200

        # Now unassign succeeds — read the latest asset version first.
        latest_response = client.get(f"/api/v1/assets/{asset_id}", headers=manager_auth)
        assert latest_response.status_code == 200, latest_response.text
        latest_asset = latest_response.json()["data"]
        assert latest_asset["status"] == "in_use"

        unassigned = client.post(
            f"/api/v1/assets/{asset_id}/unassign",
            json={
                "reason": "Now safe — repair completed.",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "version": latest_asset["version"],
            },
            headers=manager_auth,
        )
        assert unassigned.status_code == 200
        assert unassigned.json()["data"]["status"] == "in_stock"

    def test_rejected_repair_does_not_block_unassign(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Counter-test to ``test_active_repair_blocks_unassign_until_completed``.

        The cross-resource lock must apply ONLY to repair requests in
        active states (pending_review, under_repair). A terminated request
        — whether rejected or completed — must not keep the asset hostage
        forever. The single-step test
        ``test_inactive_repair_request_does_not_block`` in test_assets.py
        already covers this for an arbitrary "inactive" row, but it builds
        the row directly in the DB. This journey proves the same property
        end-to-end: an actual reject flow leaves the asset unlocked.

        Risk it defends: a future refactor that filters "blocking repair
        requests" by ``deleted_at IS NULL`` only (instead of also
        excluding terminal statuses) would silently keep rejected requests
        as eternal locks.
        """
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        manager_auth = auth_headers(manager)
        holder_auth = auth_headers(holder)

        assigned = _register_and_assign_via_api(client, manager_auth, holder)
        asset_id = assigned["id"]

        submit_resp = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset_id,
                "fault_description": "Possibly a thermal issue.",
                "version": assigned["version"],
            },
            headers=holder_auth,
        )
        assert submit_resp.status_code == 201, submit_resp.text
        submitted = submit_resp.json()["data"]

        # Manager rejects the request, returning the asset to in_use.
        reject_resp = client.post(
            f"/api/v1/repair-requests/{submitted['id']}/reject",
            json={
                "rejection_reason": "Could not reproduce on retest.",
                "version": submitted["version"],
            },
            headers=manager_auth,
        )
        assert reject_resp.status_code == 200

        # The asset must now be unassignable. The rejected request is
        # still in the DB (audit trail) but its terminal status means it
        # no longer counts as a "blocking" record.
        current_asset_resp = client.get(f"/api/v1/assets/{asset_id}", headers=manager_auth)
        assert current_asset_resp.status_code == 200, current_asset_resp.text
        current_asset = current_asset_resp.json()["data"]
        assert current_asset["status"] == "in_use"

        unassign_resp = client.post(
            f"/api/v1/assets/{asset_id}/unassign",
            json={
                "reason": "Holder leaving anyway.",
                "unassignment_date": _UNASSIGNMENT_DATE_ISO,
                "version": current_asset["version"],
            },
            headers=manager_auth,
        )
        assert unassign_resp.status_code == 200
        assert unassign_resp.json()["data"]["status"] == "in_stock"

    def test_active_repair_blocks_dispose_until_completed(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Same cross-resource lock applies to dispose.

        Dispose is more dangerous than unassign — it's terminal — so the
        guard matters even more here. We confirm it kicks in for a repair
        request in ``pending_review`` (no approval needed; the very act of
        being open blocks dispose).
        """
        manager = make_user(role=UserRole.MANAGER)
        holder = make_user(role=UserRole.HOLDER)
        manager_auth = auth_headers(manager)
        holder_auth = auth_headers(holder)

        assigned = _register_and_assign_via_api(client, manager_auth, holder)
        asset_id = assigned["id"]

        submit_resp = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset_id,
                "fault_description": "Battery does not charge.",
                "version": assigned["version"],
            },
            headers=holder_auth,
        )
        assert submit_resp.status_code == 201

        # An asset in pending_repair cannot be disposed — also fails the
        # in_stock prerequisite for dispose, so the FSM guard returns 409.
        current_asset_resp = client.get(f"/api/v1/assets/{asset_id}", headers=manager_auth)
        assert current_asset_resp.status_code == 200, current_asset_resp.text
        current_asset = current_asset_resp.json()["data"]
        blocked_dispose = client.post(
            f"/api/v1/assets/{asset_id}/dispose",
            json={
                "disposal_reason": "Trying to dispose mid-repair.",
                "version": current_asset["version"],
            },
            headers=manager_auth,
        )
        assert blocked_dispose.status_code == 409
        assert blocked_dispose.json()["error"]["code"] == "invalid_transition"

        # Verify the failed 409 did NOT mutate the asset. Dispose is
        # terminal; a silent execution behind a 409 would be catastrophic.
        unchanged_resp = client.get(f"/api/v1/assets/{asset_id}", headers=manager_auth)
        assert unchanged_resp.status_code == 200, unchanged_resp.text
        unchanged_asset = unchanged_resp.json()["data"]
        assert unchanged_asset["status"] == current_asset["status"]
        assert unchanged_asset["disposal_reason"] is None
        assert unchanged_asset["version"] == current_asset["version"]
