"""Parametrized FSM matrix tests for asset + repair-request transitions.

Why this file exists alongside the per-endpoint transition tests in
``test_assets.py`` / ``test_repair_requests.py``: those tests verify
**specific** transitions one at a time, which means a missing test for
a newly-added transition just slips through code review. The matrix
below is the single executable counterpart to
``docs/system-design/11-asset-fsm.md`` — adding a new transition means
adding a row here, and a missing row makes the failure mode obvious
(the new transition is implemented but no test asserts it).

The two tables (asset-action matrix + repair-action matrix) together
cover **every (state, action) cell** in the FSM diagram:

- Legal cells assert ``200/201`` and the post-call state.
- Illegal cells assert ``4xx`` (the specific code is part of the row,
  not derived) and that the row is otherwise unchanged.

If the FSM table evolves (e.g. a new state, or a transition swaps
direction), the corresponding row(s) here must be edited in the same
commit — otherwise the test catches the divergence the next run.

This is the standard "FSM matrix" pattern used at mid-senior level in
the wild: state machines are one of the highest-density bug surfaces
in any domain app, and a table-driven test forces the spec and the
test to live in lockstep.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole

# Short aliases so the FSM matrix tables stay readable inside ruff's
# 100-char line budget. Used only inside this file.
_AS = AssetStatus
_RS = RepairRequestStatus

# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------
#
# Each FSM state has a canonical "what the rest of the row looks like"
# invariant (in_use must have a holder; pending_repair must have an
# active RR; disposed must have responsible_person_id = NULL). The
# helpers below build a starting state that satisfies those invariants
# so the test exercises the actual state guard, not a contrived database
# row that the production app would never produce.
# ---------------------------------------------------------------------------

_PURCHASE_DATE = date(2026, 1, 1)
_ASSIGN_DATE = date(2026, 2, 1)


def _build_asset(status: AssetStatus, holder: User | None) -> Asset:
    """Return an unsaved Asset wired with the right side-fields for ``status``.

    ``in_stock`` / ``disposed`` keep ``responsible_person_id`` NULL
    because that is what the production state machine actually writes.
    ``in_use`` / ``pending_repair`` / ``under_repair`` keep the holder
    attached, because those states only exist after a successful
    assignment and the production code never clears the FK until
    unassign/dispose.
    """
    asset = Asset(
        asset_code=f"AST-FSM-{uuid.uuid4().hex[:8]}",
        name="FSM matrix test asset",
        model="X",
        category="computer",
        supplier="ACME",
        purchase_date=_PURCHASE_DATE,
        purchase_amount=Decimal("1000.00"),
        location="HQ",
        department="IT",
        status=status,
    )
    if status in {AssetStatus.IN_USE, AssetStatus.PENDING_REPAIR, AssetStatus.UNDER_REPAIR}:
        assert holder is not None, "non-stock states require a holder"
        asset.responsible_person_id = holder.id
        asset.assignment_date = _ASSIGN_DATE
    return asset


def _seed_asset_in_state(
    db: Session,
    state: AssetStatus,
    *,
    holder: User,
    manager: User,
) -> tuple[Asset, RepairRequest | None]:
    """Persist an asset (and, where required, its in-flight repair request).

    Returns the asset and (for the two repair states) the row that
    proves there's actually an active request — so the test can assert
    later that the row is or isn't touched.
    """
    asset = _build_asset(state, holder)
    db.add(asset)
    db.flush()

    rr: RepairRequest | None = None
    if state is AssetStatus.PENDING_REPAIR:
        rr = RepairRequest(
            repair_id=f"REP-FSM-{uuid.uuid4().hex[:8]}",
            asset_id=asset.id,
            requester_id=holder.id,
            status=RepairRequestStatus.PENDING_REVIEW,
            fault_description="seed: pending_review",
        )
        db.add(rr)
    elif state is AssetStatus.UNDER_REPAIR:
        rr = RepairRequest(
            repair_id=f"REP-FSM-{uuid.uuid4().hex[:8]}",
            asset_id=asset.id,
            requester_id=holder.id,
            reviewer_id=manager.id,
            status=RepairRequestStatus.UNDER_REPAIR,
            fault_description="seed: under_repair",
        )
        db.add(rr)

    db.commit()
    db.refresh(asset)
    if rr is not None:
        db.refresh(rr)
    return asset, rr


def _seed_repair_request_in_state(
    db: Session,
    state: RepairRequestStatus,
    *,
    holder: User,
    manager: User,
) -> tuple[Asset, RepairRequest]:
    """Persist an RR in the requested state with a coherent asset row.

    The paired asset state follows the FSM: ``pending_review`` ⇆
    ``pending_repair`` asset, ``under_repair`` ⇆ ``under_repair`` asset,
    ``completed`` / ``rejected`` ⇆ ``in_use`` asset (terminal RR states
    leave the asset back in normal use).
    """
    asset_state = {
        RepairRequestStatus.PENDING_REVIEW: AssetStatus.PENDING_REPAIR,
        RepairRequestStatus.UNDER_REPAIR: AssetStatus.UNDER_REPAIR,
        RepairRequestStatus.COMPLETED: AssetStatus.IN_USE,
        RepairRequestStatus.REJECTED: AssetStatus.IN_USE,
    }[state]
    asset = _build_asset(asset_state, holder)
    db.add(asset)
    db.flush()

    rr = RepairRequest(
        repair_id=f"REP-FSM-{uuid.uuid4().hex[:8]}",
        asset_id=asset.id,
        requester_id=holder.id,
        status=state,
        fault_description=f"seed: {state.value}",
    )
    if state is not RepairRequestStatus.PENDING_REVIEW:
        # PENDING_REVIEW has never been touched by a reviewer yet; every
        # other terminal/transitional state has been claimed by a manager.
        rr.reviewer_id = manager.id
    if state is RepairRequestStatus.REJECTED:
        rr.rejection_reason = "seed: rejected"
    db.add(rr)
    db.commit()
    db.refresh(asset)
    db.refresh(rr)
    return asset, rr


# ---------------------------------------------------------------------------
# Asset-action matrix
# ---------------------------------------------------------------------------

_AssetAction = Literal["assign", "unassign", "dispose", "submit_repair"]


_ASSET_FSM_MATRIX: list[tuple[str, AssetStatus, _AssetAction, int, AssetStatus]] = [
    # T2: assign — legal only from in_stock
    ("T2-in_stock", _AS.IN_STOCK, "assign", 200, _AS.IN_USE),
    ("T2-in_use", _AS.IN_USE, "assign", 409, _AS.IN_USE),
    ("T2-pending_repair", _AS.PENDING_REPAIR, "assign", 409, _AS.PENDING_REPAIR),
    ("T2-under_repair", _AS.UNDER_REPAIR, "assign", 409, _AS.UNDER_REPAIR),
    ("T2-disposed", _AS.DISPOSED, "assign", 409, _AS.DISPOSED),
    # T5: unassign — legal only from in_use (and no active repair, which
    # is implicitly true for ``in_use`` by the seeding invariant)
    ("T5-in_stock", _AS.IN_STOCK, "unassign", 409, _AS.IN_STOCK),
    ("T5-in_use", _AS.IN_USE, "unassign", 200, _AS.IN_STOCK),
    ("T5-pending_repair", _AS.PENDING_REPAIR, "unassign", 409, _AS.PENDING_REPAIR),
    ("T5-under_repair", _AS.UNDER_REPAIR, "unassign", 409, _AS.UNDER_REPAIR),
    ("T5-disposed", _AS.DISPOSED, "unassign", 409, _AS.DISPOSED),
    # T3: dispose — legal only from in_stock with no holder and no
    # active repair (both implied by the in_stock seeding invariant)
    ("T3-in_stock", _AS.IN_STOCK, "dispose", 200, _AS.DISPOSED),
    ("T3-in_use", _AS.IN_USE, "dispose", 409, _AS.IN_USE),
    ("T3-pending_repair", _AS.PENDING_REPAIR, "dispose", 409, _AS.PENDING_REPAIR),
    ("T3-under_repair", _AS.UNDER_REPAIR, "dispose", 409, _AS.UNDER_REPAIR),
    ("T3-disposed", _AS.DISPOSED, "dispose", 409, _AS.DISPOSED),
    # T4: submit_repair — legal only when the holder owns the asset
    # AND the asset is in_use. The ``in_stock`` / ``disposed`` rows have
    # no holder so they reject with 403 (RBAC-flavoured "not your
    # asset") before the FSM check ever runs; that is the production
    # behaviour we want to lock in.
    ("T4-in_stock", _AS.IN_STOCK, "submit_repair", 403, _AS.IN_STOCK),
    ("T4-in_use", _AS.IN_USE, "submit_repair", 201, _AS.PENDING_REPAIR),
    ("T4-pending_repair", _AS.PENDING_REPAIR, "submit_repair", 409, _AS.PENDING_REPAIR),
    ("T4-under_repair", _AS.UNDER_REPAIR, "submit_repair", 409, _AS.UNDER_REPAIR),
    ("T4-disposed", _AS.DISPOSED, "submit_repair", 403, _AS.DISPOSED),
]


def _call_asset_action(
    client: TestClient,
    *,
    action: _AssetAction,
    asset: Asset,
    holder: User,
    holder_headers: dict[str, str],
    manager_headers: dict[str, str],
) -> int:
    """Invoke the endpoint corresponding to ``action`` and return its status.

    Centralised so the matrix test stays free of URL / payload detail —
    every cell expresses the FSM claim and nothing else.
    """
    if action == "assign":
        response = client.post(
            f"/api/v1/assets/{asset.id}/assign",
            headers=manager_headers,
            json={
                "responsible_person_id": holder.id,
                "assignment_date": _ASSIGN_DATE.isoformat(),
                "version": asset.version,
            },
        )
    elif action == "unassign":
        response = client.post(
            f"/api/v1/assets/{asset.id}/unassign",
            headers=manager_headers,
            json={
                "reason": "FSM matrix test",
                "unassignment_date": date(2026, 3, 1).isoformat(),
                "version": asset.version,
            },
        )
    elif action == "dispose":
        response = client.post(
            f"/api/v1/assets/{asset.id}/dispose",
            headers=manager_headers,
            json={"disposal_reason": "FSM matrix test", "version": asset.version},
        )
    elif action == "submit_repair":
        response = client.post(
            "/api/v1/repair-requests",
            headers=holder_headers,
            json={
                "asset_id": asset.id,
                "fault_description": "FSM matrix submit",
                "version": asset.version,
            },
        )
    else:
        # Defensive guard: if a row in _ASSET_FSM_MATRIX is mistyped or a
        # new _AssetAction literal is added without a dispatch branch,
        # the test would otherwise crash with ``UnboundLocalError`` on
        # ``response`` — a confusing error that hides the real bug.
        # Fail loudly with the offending action name instead.
        raise AssertionError(f"unknown asset FSM action: {action!r}")
    return response.status_code


class TestAssetFSMMatrix:
    """One row per (asset state, asset action) cell from 11-asset-fsm.md.

    The four asset-state-driven actions (assign, unassign, dispose,
    submit_repair) are all covered. ``approve`` / ``reject`` /
    ``complete`` are keyed off the repair-request state, not the
    asset state directly, so they live in ``TestRepairFSMMatrix``
    below.
    """

    @pytest.mark.parametrize(
        ("transition_id", "from_state", "action", "expected_status", "expected_to_state"),
        [pytest.param(*row, id=row[0]) for row in _ASSET_FSM_MATRIX],
    )
    def test_asset_transition(
        self,
        transition_id: str,
        from_state: AssetStatus,
        action: _AssetAction,
        expected_status: int,
        expected_to_state: AssetStatus,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER, name=f"H-{transition_id}")
        manager = make_user(role=UserRole.MANAGER, name=f"M-{transition_id}")
        asset, _ = _seed_asset_in_state(db_session, from_state, holder=holder, manager=manager)

        actual_status = _call_asset_action(
            client,
            action=action,
            asset=asset,
            holder=holder,
            holder_headers=auth_headers(holder),
            manager_headers=auth_headers(manager),
        )

        # The response says the call was rejected/accepted — now prove
        # the row actually moved (or didn't). The DB-side assertion is
        # the one that catches "endpoint returned 409 but the write got
        # through anyway" bugs, which are exactly the bugs single-step
        # tests miss.
        db_session.refresh(asset)
        assert actual_status == expected_status, (
            f"{transition_id}: expected HTTP {expected_status}, got {actual_status}"
        )
        assert asset.status is expected_to_state, (
            f"{transition_id}: expected asset state {expected_to_state.value}, "
            f"got {asset.status.value if asset.status else None}"
        )


# ---------------------------------------------------------------------------
# Repair-action matrix
# ---------------------------------------------------------------------------

_RepairAction = Literal["approve", "reject", "complete"]


_COMPLETION_PAYLOAD = {
    "repair_date": "2026-04-20",
    "fault_content": "FSM matrix complete",
    "repair_plan": "Replaced cable",
    "repair_cost": "1500.00",
    "repair_vendor": "Vendor",
}


_REPAIR_FSM_MATRIX: list[
    tuple[str, RepairRequestStatus, _RepairAction, int, RepairRequestStatus, AssetStatus]
] = [
    # T6: approve — legal only from pending_review
    ("T6-pending_review", _RS.PENDING_REVIEW, "approve", 200, _RS.UNDER_REPAIR, _AS.UNDER_REPAIR),  # noqa: E501
    ("T6-under_repair", _RS.UNDER_REPAIR, "approve", 409, _RS.UNDER_REPAIR, _AS.UNDER_REPAIR),  # noqa: E501
    ("T6-completed", _RS.COMPLETED, "approve", 409, _RS.COMPLETED, _AS.IN_USE),
    ("T6-rejected", _RS.REJECTED, "approve", 409, _RS.REJECTED, _AS.IN_USE),
    # T7: reject — legal only from pending_review
    ("T7-pending_review", _RS.PENDING_REVIEW, "reject", 200, _RS.REJECTED, _AS.IN_USE),
    ("T7-under_repair", _RS.UNDER_REPAIR, "reject", 409, _RS.UNDER_REPAIR, _AS.UNDER_REPAIR),  # noqa: E501
    ("T7-completed", _RS.COMPLETED, "reject", 409, _RS.COMPLETED, _AS.IN_USE),
    ("T7-rejected", _RS.REJECTED, "reject", 409, _RS.REJECTED, _AS.IN_USE),
    # T8: complete — legal only from under_repair
    (
        "T8-pending_review",
        _RS.PENDING_REVIEW,
        "complete",
        409,
        _RS.PENDING_REVIEW,
        _AS.PENDING_REPAIR,
    ),  # noqa: E501
    ("T8-under_repair", _RS.UNDER_REPAIR, "complete", 200, _RS.COMPLETED, _AS.IN_USE),
    ("T8-completed", _RS.COMPLETED, "complete", 409, _RS.COMPLETED, _AS.IN_USE),
    ("T8-rejected", _RS.REJECTED, "complete", 409, _RS.REJECTED, _AS.IN_USE),
]


def _call_repair_action(
    client: TestClient,
    *,
    action: _RepairAction,
    rr: RepairRequest,
    caller_headers: dict[str, str],
) -> int:
    """Issue the FSM-transition call for ``action`` with the given headers.

    Centralised so callers (manager-allowed transitions in
    TestRepairFSMMatrix, holder-forbidden cells in the
    cross-state safety test below) can target the same endpoints
    without copy-pasting request bodies.
    """
    if action == "approve":
        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/approve",
            headers=caller_headers,
            json={"version": rr.version},
        )
    elif action == "reject":
        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/reject",
            headers=caller_headers,
            json={"version": rr.version, "rejection_reason": "FSM matrix reject"},
        )
    elif action == "complete":
        response = client.post(
            f"/api/v1/repair-requests/{rr.id}/complete",
            headers=caller_headers,
            json={**_COMPLETION_PAYLOAD, "version": rr.version},
        )
    else:
        # Defensive guard: see _call_asset_action for rationale.
        raise AssertionError(f"unknown repair FSM action: {action!r}")
    return response.status_code


class TestRepairFSMMatrix:
    """One row per (repair-request state, repair action) cell.

    Verifies the **pair** moves correctly: both the repair_request
    and its associated asset land on the right states, or both stay
    put on rejection. A regression where the RR transitions but the
    asset row is missed (or vice versa) is exactly the half-update
    bug atomicity tests exist to catch, and the matrix makes sure
    that check fires for every illegal entry, not just the ones a
    developer remembered to enumerate.
    """

    @pytest.mark.parametrize(
        (
            "transition_id",
            "from_state",
            "action",
            "expected_status",
            "expected_to_state",
            "expected_asset_state",
        ),
        [pytest.param(*row, id=row[0]) for row in _REPAIR_FSM_MATRIX],
    )
    def test_repair_transition(
        self,
        transition_id: str,
        from_state: RepairRequestStatus,
        action: _RepairAction,
        expected_status: int,
        expected_to_state: RepairRequestStatus,
        expected_asset_state: AssetStatus,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER, name=f"H-{transition_id}")
        manager = make_user(role=UserRole.MANAGER, name=f"M-{transition_id}")
        asset, rr = _seed_repair_request_in_state(
            db_session, from_state, holder=holder, manager=manager
        )

        actual_status = _call_repair_action(
            client,
            action=action,
            rr=rr,
            caller_headers=auth_headers(manager),
        )

        db_session.refresh(rr)
        db_session.refresh(asset)
        assert actual_status == expected_status, (
            f"{transition_id}: expected HTTP {expected_status}, got {actual_status}"
        )
        assert rr.status is expected_to_state, (
            f"{transition_id}: expected RR state {expected_to_state.value}, got {rr.status.value}"
        )
        assert asset.status is expected_asset_state, (
            f"{transition_id}: expected asset state {expected_asset_state.value}, "
            f"got {asset.status.value}"
        )

    # ------------------------------------------------------------------
    # Cross-state holder-forbidden guard
    # ------------------------------------------------------------------
    #
    # test_rbac_matrix.py only covers approve/reject/complete from the
    # seeded ``pending_review`` state. A regression where the holder
    # gate is removed from these endpoints only *after* the RR moves to
    # ``under_repair`` (e.g. a state-conditional auth dep that ships
    # broken) would silently pass the RBAC matrix. The cells below
    # exhaustively assert that a holder gets 403 for every
    # (action × from_state) cell, AND that the rejected call does NOT
    # mutate either the RR or the asset row.
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("transition_id", "from_state", "action"),
        [
            pytest.param(
                f"holder-forbidden-{row[0]}",
                row[1],
                row[2],
                id=f"holder-{row[0]}",
            )
            for row in _REPAIR_FSM_MATRIX
        ],
    )
    def test_holder_forbidden_for_every_repair_action(
        self,
        transition_id: str,
        from_state: RepairRequestStatus,
        action: _RepairAction,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Every (action × from_state) cell must 403 for a holder caller.

        Two-part assertion: the gate returns 403 (not 401, not 409 — a
        409 would imply the holder *passed* the gate and then failed
        the FSM check, which is the regression we are guarding against)
        AND the row state is unchanged.
        """
        holder = make_user(role=UserRole.HOLDER, name=f"H-{transition_id}")
        manager = make_user(role=UserRole.MANAGER, name=f"M-{transition_id}")
        asset, rr = _seed_repair_request_in_state(
            db_session, from_state, holder=holder, manager=manager
        )
        rr_status_before = rr.status
        asset_status_before = asset.status
        rr_version_before = rr.version

        actual_status = _call_repair_action(
            client,
            action=action,
            rr=rr,
            caller_headers=auth_headers(holder),
        )

        db_session.refresh(rr)
        db_session.refresh(asset)
        assert actual_status == 403, (
            f"{transition_id}: holder called {action} from {from_state.value} — "
            f"expected HTTP 403 from the role gate, got {actual_status}."
        )
        assert rr.status is rr_status_before, (
            f"{transition_id}: forbidden call mutated RR status from "
            f"{rr_status_before.value} to {rr.status.value}"
        )
        assert asset.status is asset_status_before, (
            f"{transition_id}: forbidden call mutated asset status from "
            f"{asset_status_before.value} to {asset.status.value}"
        )
        assert rr.version == rr_version_before, (
            f"{transition_id}: forbidden call bumped RR version {rr_version_before} -> {rr.version}"
        )
