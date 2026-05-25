"""Parametrized RBAC matrix — one row per endpoint, asserting whether
each of {anonymous, holder, manager} is permitted to call it.

Why this file exists alongside per-endpoint 401/403 tests in
``test_assets.py`` / ``test_repair_requests.py`` / ``test_auth_*``:
those tests check **specific** endpoints in isolation, so adding a
new endpoint and forgetting to attach an auth dep just slips through
code review. The matrix below is the single executable counterpart to
the RBAC policy in ``docs/system-design/12-api-design.md``: adding a
new endpoint means adding a row, and a missing row makes the gap
obvious instead of disappearing into a sea of similar test files.

For each (endpoint, role) cell:
- ``allowed=True``  → the response **must** be anything other than
  ``401 / 403``. Passing the gate is what's measured here, not what
  happens after — a body-validation 422 or a business-logic 409 still
  count as "the auth dep let us through".
- ``allowed=False`` → the response **must** be ``401`` (anonymous) or
  ``403`` (wrong role).

Industry pattern: this is what mid-senior backend engineers call a
"RBAC matrix test" and it's the standard answer to interview questions
about how you ensure permissions don't regress. The matrix doubles as
documentation — a reviewer can read it in 30 seconds and know who can
call what.

Note on body construction: many endpoints declare Pydantic body
parameters before their auth dep. FastAPI resolves dependencies in
declaration order, so anonymous calls with an **invalid** body would
get 422 from Pydantic before the 401 from the auth dep — which would
let a missing auth dep slip past a permissive "anon-blocked" check.
Every row therefore sends a minimally-valid body to guarantee the
auth dep is the only gate that fires.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any, NamedTuple

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.repair_image import RepairImage
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Matrix shape
# ---------------------------------------------------------------------------

# We model "permitted to pass the auth gate" rather than "expected exact
# status code" because a single row would otherwise have to enumerate
# every business-logic outcome (200, 201, 404, 409, 422, …) for each
# role × endpoint combination. The RBAC policy is binary per cell — the
# matrix should be too.
_GATE_REJECT_CODES = frozenset({401, 403})


class _RbacCase(NamedTuple):
    """One row of the RBAC matrix."""

    method: str
    path_template: str
    # ``None`` for GET / endpoints that read the body manually. A dict
    # (possibly empty) for endpoints where FastAPI's Pydantic body
    # validation must succeed before the auth dep runs. String values
    # are passed through ``str.format(**context)`` at call time so
    # IDs from the seeded fixtures can be threaded in.
    body: dict[str, Any] | None
    allow_anon: bool
    allow_holder: bool
    allow_manager: bool


def _substitute(value: Any, context: dict[str, Any]) -> Any:
    """Recursively format ``{placeholder}`` strings against ``context``.

    Lets the matrix store template strings like ``"{holder_id}"`` next
    to literal values so the rows stay readable; the substitution only
    fires at call time when the seeded entities exist.
    """
    if isinstance(value, str):
        return value.format(**context) if "{" in value else value
    if isinstance(value, dict):
        return {k: _substitute(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, context) for v in value]
    return value


# ---------------------------------------------------------------------------
# RBAC matrix — one row per public endpoint in app/api/v1/endpoints/*
# ---------------------------------------------------------------------------
#
# Map of who is allowed where, derived from the @router decorators and
# the auth deps (CurrentUser / HolderUser / ManagerUser) they each
# declare. The intent is that this table is the *source of truth*:
# changing an endpoint's required role MUST flip a flag here, and a
# missing endpoint must add a row. Drift between code and this matrix
# is exactly the regression class the test is designed to catch.
# ---------------------------------------------------------------------------

_RBAC_MATRIX: list[_RbacCase] = [
    # -----------------------------------------------------------------
    # /api/v1/auth/* — public + manager admin escape hatch
    # -----------------------------------------------------------------
    _RbacCase(
        "POST", "/api/v1/auth/login",
        body={"email": "{holder_email}", "password": "Password123"},
        allow_anon=True, allow_holder=True, allow_manager=True,
    ),
    _RbacCase(
        "POST", "/api/v1/auth/register",
        # Each call must use a unique email to avoid a 409 from the
        # second + third role hitting the same row. ``{nonce}`` is a
        # per-call UUID injected by the test, not a fixture value.
        body={
            "email": "rbac-{nonce}@example.com",
            "password": "Password123",
            "name": "RBAC Tester",
            "department": "QA",
        },
        allow_anon=True, allow_holder=True, allow_manager=True,
    ),
    _RbacCase(
        "GET", "/api/v1/auth/me",
        body=None,
        allow_anon=False, allow_holder=True, allow_manager=True,
    ),
    _RbacCase(
        "POST", "/api/v1/auth/users",
        body={
            "email": "admin-create-{nonce}@example.com",
            "password": "Password123",
            "name": "Admin-created",
            "department": "QA",
            "role": "holder",
        },
        allow_anon=False, allow_holder=False, allow_manager=True,
    ),

    # -----------------------------------------------------------------
    # /api/v1/users
    # -----------------------------------------------------------------
    _RbacCase(
        "GET", "/api/v1/users",
        body=None,
        allow_anon=False, allow_holder=False, allow_manager=True,
    ),

    # -----------------------------------------------------------------
    # /api/v1/assets/*
    # -----------------------------------------------------------------
    _RbacCase(
        "GET", "/api/v1/assets",
        body=None,
        allow_anon=False, allow_holder=False, allow_manager=True,
    ),
    _RbacCase(
        "POST", "/api/v1/assets",
        body={
            "name": "RBAC Asset", "model": "RBAC-X", "category": "computer",
            "supplier": "ACME", "purchase_date": "2026-01-01",
            "purchase_amount": "100.00",
        },
        allow_anon=False, allow_holder=False, allow_manager=True,
    ),
    _RbacCase(
        "GET", "/api/v1/assets/mine",
        body=None,
        allow_anon=False, allow_holder=True, allow_manager=False,
    ),
    _RbacCase(
        "GET", "/api/v1/assets/{asset_id}",
        body=None,
        allow_anon=False, allow_holder=True, allow_manager=True,
    ),
    _RbacCase(
        "GET", "/api/v1/assets/{asset_id}/history",
        body=None,
        allow_anon=False, allow_holder=False, allow_manager=True,
    ),
    _RbacCase(
        "PATCH", "/api/v1/assets/{asset_id}",
        body={"version": 1},
        allow_anon=False, allow_holder=False, allow_manager=True,
    ),
    _RbacCase(
        "POST", "/api/v1/assets/{asset_id}/assign",
        body={
            "responsible_person_id": "{holder_id}",
            "assignment_date": "2026-02-01",
            "version": 1,
        },
        allow_anon=False, allow_holder=False, allow_manager=True,
    ),
    _RbacCase(
        "POST", "/api/v1/assets/{asset_id}/unassign",
        body={
            "reason": "RBAC test",
            "unassignment_date": "2026-04-01",
            "version": 2,
        },
        allow_anon=False, allow_holder=False, allow_manager=True,
    ),
    _RbacCase(
        "POST", "/api/v1/assets/{asset_id}/dispose",
        body={"disposal_reason": "RBAC test", "version": 2},
        allow_anon=False, allow_holder=False, allow_manager=True,
    ),

    # -----------------------------------------------------------------
    # /api/v1/repair-requests/*
    #
    # POST /repair-requests is the multipart submit endpoint; its
    # function reads the request body manually, so there is no
    # Pydantic body extractor running before the auth dep. ``body=None``
    # is correct here — anonymous calls still hit the auth dep first.
    # -----------------------------------------------------------------
    _RbacCase(
        "GET", "/api/v1/repair-requests",
        body=None,
        allow_anon=False, allow_holder=True, allow_manager=True,
    ),
    _RbacCase(
        "POST", "/api/v1/repair-requests",
        body=None,
        allow_anon=False, allow_holder=True, allow_manager=False,
    ),
    _RbacCase(
        "GET", "/api/v1/repair-requests/{rr_id}",
        body=None,
        allow_anon=False, allow_holder=True, allow_manager=True,
    ),
    _RbacCase(
        "POST", "/api/v1/repair-requests/{rr_id}/approve",
        body={"version": 1},
        allow_anon=False, allow_holder=False, allow_manager=True,
    ),
    _RbacCase(
        "POST", "/api/v1/repair-requests/{rr_id}/reject",
        body={"version": 1, "rejection_reason": "RBAC test"},
        allow_anon=False, allow_holder=False, allow_manager=True,
    ),
    _RbacCase(
        "POST", "/api/v1/repair-requests/{rr_id}/complete",
        body={
            "repair_date": "2026-04-20",
            "fault_content": "rbac",
            "repair_plan": "rbac",
            "repair_cost": "100.00",
            "repair_vendor": "rbac",
            "version": 1,
        },
        allow_anon=False, allow_holder=False, allow_manager=True,
    ),
    _RbacCase(
        "PATCH", "/api/v1/repair-requests/{rr_id}/repair-details",
        body={"fault_content": "rbac", "version": 1},
        allow_anon=False, allow_holder=False, allow_manager=True,
    ),

    # -----------------------------------------------------------------
    # /api/v1/images/{image_id}
    # -----------------------------------------------------------------
    _RbacCase(
        "GET", "/api/v1/images/{image_id}",
        body=None,
        allow_anon=False, allow_holder=True, allow_manager=True,
    ),
]


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_rbac_world(
    db: Session, holder: User
) -> tuple[Asset, RepairRequest, RepairImage]:
    """Persist the minimum entities the matrix needs path params for.

    One asset assigned to ``holder`` plus a pending-review repair
    request and a placeholder image row. Everything else (per-call
    state changes, validation failures) is irrelevant to the gate
    measurement — the matrix only cares about ``401`` vs ``403`` vs
    "passed".
    """
    asset = Asset(
        asset_code=f"AST-RBAC-{uuid.uuid4().hex[:8]}",
        name="RBAC seed asset",
        model="X",
        category="computer",
        supplier="ACME",
        purchase_date=date(2026, 1, 1),
        purchase_amount=Decimal("1000.00"),
        location="HQ",
        department="IT",
        status=AssetStatus.PENDING_REPAIR,
        responsible_person_id=holder.id,
        assignment_date=date(2026, 2, 1),
    )
    db.add(asset)
    db.flush()

    rr = RepairRequest(
        repair_id=f"REP-RBAC-{uuid.uuid4().hex[:8]}",
        asset_id=asset.id,
        requester_id=holder.id,
        status=RepairRequestStatus.PENDING_REVIEW,
        fault_description="seed",
    )
    db.add(rr)
    db.flush()

    image = RepairImage(
        repair_request_id=rr.id,
        image_url=f"{rr.id}/seed.jpg",
    )
    db.add(image)
    db.commit()
    db.refresh(asset)
    db.refresh(rr)
    db.refresh(image)
    return asset, rr, image


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


_Role = str  # "anon" | "holder" | "manager"


def _matrix_param_id(case: _RbacCase, role: _Role) -> str:
    """Human-readable pytest test ID like ``POST-assets-assign[holder]``."""
    short_path = case.path_template.replace("/api/v1/", "").rstrip("/")
    return f"{case.method}-{short_path}[{role}]"


def _expand_matrix() -> list[tuple[_RbacCase, _Role, bool]]:
    """Yield (case, role, expected_allowed) triples for parametrize.

    Three role columns per row → 3× the entry count. Done eagerly so
    pytest test IDs are stable and per-row failures show up as
    individual line items in the report.
    """
    expanded: list[tuple[_RbacCase, _Role, bool]] = []
    for case in _RBAC_MATRIX:
        expanded.append((case, "anon", case.allow_anon))
        expanded.append((case, "holder", case.allow_holder))
        expanded.append((case, "manager", case.allow_manager))
    return expanded


class TestRbacMatrix:
    """One test per (endpoint, role) cell — pure gate-pass / gate-block check."""

    @pytest.mark.parametrize(
        ("case", "role", "expected_allowed"),
        [
            pytest.param(c, r, a, id=_matrix_param_id(c, r))
            for (c, r, a) in _expand_matrix()
        ],
    )
    def test_role_gate(
        self,
        case: _RbacCase,
        role: _Role,
        expected_allowed: bool,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # Fresh holder + manager per test so we do not run into the
        # bootstrap-manager email uniqueness constraint and so the
        # matrix can stay role-symmetric without leaking state.
        holder = make_user(role=UserRole.HOLDER, name="RBAC-Holder")
        manager = make_user(role=UserRole.MANAGER, name="RBAC-Manager")
        asset, rr, image = _seed_rbac_world(db_session, holder)

        context = {
            "asset_id": asset.id,
            "rr_id": rr.id,
            "image_id": image.id,
            "holder_id": holder.id,
            "holder_email": holder.email,
            "nonce": uuid.uuid4().hex[:8],
        }
        path = case.path_template.format(**context)
        body = _substitute(case.body, context) if case.body is not None else None

        headers: dict[str, str] = {}
        if role == "holder":
            headers = auth_headers(holder)
        elif role == "manager":
            headers = auth_headers(manager)

        response = client.request(case.method, path, headers=headers, json=body)

        gate_rejected = response.status_code in _GATE_REJECT_CODES
        if expected_allowed:
            assert not gate_rejected, (
                f"{case.method} {case.path_template} as {role}: expected to "
                f"pass the auth/role gate, but got HTTP {response.status_code}. "
                f"Either the matrix row is wrong, or the endpoint just lost an "
                f"auth/role dependency."
            )
        else:
            assert gate_rejected, (
                f"{case.method} {case.path_template} as {role}: expected to "
                f"be rejected at the auth/role gate (401 or 403), but got "
                f"HTTP {response.status_code}. Either the matrix row is "
                f"wrong, or the endpoint is no longer protected."
            )
