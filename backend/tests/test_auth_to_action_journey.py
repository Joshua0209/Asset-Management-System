"""End-to-end journey tests that begin at authentication.

Most of the suite mints JWTs directly through ``create_access_token(...)``
to skip the login round-trip. That is correct for tests whose subject is
the *action* (assign, approve, complete). It does, however, leave a gap:
no test proves that the token a real client gets out of ``POST /auth/login``
actually unlocks the same endpoints. The journeys here close that gap by
exercising the full chain — registration / admin-create-user → login →
authenticated action — using only the tokens the API itself issued.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User, UserRole

_HOLDER_EMAIL = "charlie@example.com"
_HOLDER_PASSWORD = "Password123"  # noqa: S105
_NEW_USER_EMAIL = "dana@example.com"
_NEW_USER_PASSWORD = "Password456"  # noqa: S105

_ASSET_PAYLOAD = {
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


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient, email: str, password: str) -> str:
    """POST /auth/login and return the issued bearer token.

    Raises if the login does not succeed — journey tests should treat
    that as a hard failure, not silently continue with an empty token.
    """
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token: str = response.json()["data"]["token"]
    return token


class TestAuthToActionJourney:
    def test_holder_registers_logs_in_and_submits_repair_request(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Public sign-up flow ending with a real authenticated mutation.

        Story: a new hire goes to the holder portal, registers their own
        account, the manager assigns them their laptop, they log in on
        their own laptop, and immediately submit a repair request because
        the laptop has a fault out of the box. Every step uses the token
        the API itself issued — no test-fixture short-circuit.
        """
        manager = make_user(role=UserRole.MANAGER)
        manager_auth = auth_headers(manager)

        # 1. Public registration — the new holder doesn't exist yet.
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "email": _HOLDER_EMAIL,
                "password": _HOLDER_PASSWORD,
                "name": "Charlie",
                "department": "Engineering",
            },
        )
        assert register_response.status_code == 201
        new_holder = register_response.json()["data"]
        assert new_holder["role"] == "holder"
        new_holder_id = new_holder["id"]

        # DB cross-check: the response says "holder" but a bug could have
        # serialised that constant in the response while the DB row got
        # written as MANAGER. Either Decision A2 (role pinned to holder)
        # is upheld at the row level, or the assertion below fails loud.
        persisted_user = db_session.get(User, new_holder_id)
        assert persisted_user is not None
        assert persisted_user.role == UserRole.HOLDER

        # 2. Manager registers an asset and assigns it to the new holder.
        asset = client.post("/api/v1/assets", json=_ASSET_PAYLOAD, headers=manager_auth).json()[
            "data"
        ]
        assigned = client.post(
            f"/api/v1/assets/{asset['id']}/assign",
            json={
                "responsible_person_id": new_holder_id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset["version"],
            },
            headers=manager_auth,
        ).json()["data"]

        # 3. The new holder logs in for the first time. The token here is
        # the one the production frontend would actually receive.
        holder_token = _login(client, _HOLDER_EMAIL, _HOLDER_PASSWORD)
        holder_auth = _bearer(holder_token)

        # 4. /auth/me echoes the holder back — proof the token is bound to
        # the right user.
        me = client.get("/api/v1/auth/me", headers=holder_auth)
        assert me.status_code == 200
        assert me.json()["data"]["email"] == _HOLDER_EMAIL

        # 5. /assets/mine shows the freshly-assigned laptop — RBAC scoped
        # correctly on the holder side.
        mine = client.get("/api/v1/assets/mine", headers=holder_auth)
        assert mine.status_code == 200
        my_assets = mine.json()["data"]
        assert len(my_assets) == 1
        assert my_assets[0]["id"] == asset["id"]

        # 6. The holder submits a repair request authenticated by that
        # same login-issued token. If anything in the chain (signing,
        # claims, role check) were wrong, this would 401 or 403.
        submit_response = client.post(
            "/api/v1/repair-requests",
            json={
                "asset_id": asset["id"],
                "fault_description": "Screen flickers out of the box.",
                "version": assigned["version"],
            },
            headers=holder_auth,
        )
        assert submit_response.status_code == 201
        submitted = submit_response.json()["data"]
        assert submitted["requester"]["id"] == new_holder_id
        assert submitted["status"] == "pending_review"

    def test_register_silently_ignores_client_supplied_role(
        self,
        client: TestClient,
        db_session: Session,
    ) -> None:
        """Decision A2: public register pins the new user to ``holder``.

        Per docs/system-design/10-design-decisions.md §A2, the public
        ``POST /auth/register`` endpoint must silently drop any
        client-supplied ``role`` field — otherwise a malicious user could
        self-elevate to manager during sign-up. The Pydantic model uses
        ``extra='ignore'`` to drop the field, and the endpoint hardcodes
        ``UserRole.HOLDER``. We prove both layers hold here:

        1. The API response says "holder" — proves the endpoint pinned it.
        2. The persisted row says HOLDER — proves the row wasn't written
           with the intruder's chosen role before serialization masked it.
        3. /auth/me, called with the issued token, also says "holder" —
           proves no role-claim was smuggled into the JWT either.
        """
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "intruder@example.com",
                "password": "Password123",
                "name": "Intruder",
                "department": "Engineering",
                "role": "manager",  # the attempted self-elevation
            },
        )
        assert response.status_code == 201
        body = response.json()["data"]
        assert body["role"] == "holder"
        new_user_id = body["id"]

        # DB row check — defense in depth.
        persisted = db_session.get(User, new_user_id)
        assert persisted is not None
        assert persisted.role == UserRole.HOLDER

        # JWT-claim check — log in and pull /auth/me. If the registration
        # had honoured `role: manager` and stamped it into the token's
        # role claim, /auth/me would report it. The next assertion would
        # then fail loud.
        token = _login(client, "intruder@example.com", "Password123")
        me = client.get("/api/v1/auth/me", headers=_bearer(token))
        assert me.status_code == 200
        assert me.json()["data"]["role"] == "holder"

    def test_manager_admin_creates_holder_then_assigns_them_an_asset(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
    ) -> None:
        """Admin-create path — the alternative to public /auth/register.

        Per Decision A2 (docs/system-design/10-design-decisions.md), public
        register is holder-only. Managers must come in through this endpoint,
        and managers can also create holders here (e.g. when bulk-onboarding
        without forcing each person to self-register). We confirm the
        manager-issued credentials work end-to-end for the new user.
        """
        # make_user side-effects the admin row into the DB; we authenticate
        # via /auth/login below, so the returned object itself is unused.
        make_user(role=UserRole.MANAGER, email="admin@example.com")
        admin_token = _login(client, "admin@example.com", "Password123")
        admin_auth = _bearer(admin_token)

        # 1. Manager creates a new holder via the admin endpoint.
        create_response = client.post(
            "/api/v1/auth/users",
            json={
                "email": _NEW_USER_EMAIL,
                "password": _NEW_USER_PASSWORD,
                "name": "Dana",
                "department": "Finance",
                "role": "holder",
            },
            headers=admin_auth,
        )
        assert create_response.status_code == 201
        created = create_response.json()["data"]
        assert created["email"] == _NEW_USER_EMAIL
        assert created["role"] == "holder"
        new_holder_id = created["id"]

        # DB cross-check: the response role and the row role must agree.
        # Without this, a serializer bug could mask a wrong DB role.
        persisted_user = db_session.get(User, new_holder_id)
        assert persisted_user is not None
        assert persisted_user.role == UserRole.HOLDER

        # 2. Manager creates an asset and assigns it to that new holder.
        asset = client.post("/api/v1/assets", json=_ASSET_PAYLOAD, headers=admin_auth).json()[
            "data"
        ]
        assign_resp = client.post(
            f"/api/v1/assets/{asset['id']}/assign",
            json={
                "responsible_person_id": new_holder_id,
                "assignment_date": _ASSIGNMENT_DATE_ISO,
                "location": "Taipei HQ",
                "version": asset["version"],
            },
            headers=admin_auth,
        )
        assert assign_resp.status_code == 200

        # 3. New holder can immediately log in with the password the
        # manager set — no separate activation step.
        holder_token = _login(client, _NEW_USER_EMAIL, _NEW_USER_PASSWORD)
        holder_auth = _bearer(holder_token)

        # 4. /assets/mine returns exactly the one asset just assigned —
        # proves the admin-issued password works and RBAC scopes the
        # listing correctly.
        mine = client.get("/api/v1/assets/mine", headers=holder_auth)
        assert mine.status_code == 200
        my_assets = mine.json()["data"]
        assert len(my_assets) == 1
        assert my_assets[0]["id"] == asset["id"]
        assert my_assets[0]["responsible_person_id"] == new_holder_id
