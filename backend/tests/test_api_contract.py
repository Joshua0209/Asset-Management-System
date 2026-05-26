"""API contract drift detector.

FastAPI auto-generates an OpenAPI schema from the route's
``response_model=...`` declarations. That schema is what the frontend
TypeScript codegen, the docs site, and any external API consumer pin
themselves against. When a handler **returns** something that does not
match the **declared** schema (extra field, wrong type, missing required
key), every other test in the suite still passes — because they only
check the specific fields they care about — but a downstream consumer
that uses the schema as ground truth will break.

This file walks a handful of representative endpoints, hits them with
the real ``TestClient`` and the existing fixtures, then validates every
response against the path operation's declared OpenAPI schema using
``jsonschema``. Happy paths AND error envelopes are validated — error
envelopes especially, because they are produced by a global handler
(see ``app/main.py``'s ``HTTPException`` handler) that lives one level
above ``response_model``, so drift between the declared
``ErrorResponse`` and what the handler emits would otherwise go unseen.

Why these endpoints: one per declared response shape we actually ship
to the frontend (paginated list, single resource read, login token
bundle, register-yields-user, generic error envelope on 401/403). If a
new shape is added (e.g. a streaming endpoint), add a test here.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy.orm import Session

from app.main import app
from app.models.asset import Asset, AssetStatus
from app.models.user import User, UserRole
from app.services.image_storage import ImageStorageError, get_image_storage

# Cache the OpenAPI document at module load. ``app.openapi()`` is
# cached internally by FastAPI but constructing the dict still costs
# a few milliseconds; doing it once per session keeps the per-test
# overhead minimal.
_OPENAPI_SCHEMA: dict[str, Any] = app.openapi()


def _inline_refs(node: Any, root: dict[str, Any]) -> Any:
    """Replace every ``{"$ref": "#/path/to/X"}`` in ``node`` with X.

    Why we do this instead of using ``jsonschema`` ``Registry``: the
    OpenAPI ``$ref`` form (``#/components/schemas/Foo``) does not
    naturally fit ``referencing.Registry``'s URI-based lookup model
    — registering the OpenAPI doc under the empty URI still fails
    ``PointerToNowhere`` because the validator binds the schema
    root to the inner sub-schema, not the document root.

    Inlining is correct and cheap here because the OpenAPI document
    is fully self-contained (no external schemas) and small enough
    (~50 components) that walking it once per test is negligible.

    The function is intentionally pure and recursive — it returns a
    new object rather than mutating ``node`` in place, so the cached
    ``_OPENAPI_SCHEMA`` stays untouched and reusable.
    """
    if isinstance(node, dict):
        if list(node.keys()) == ["$ref"]:
            ref = node["$ref"]
            if not ref.startswith("#/"):
                raise ValueError(f"Only local refs supported, got {ref!r}")
            target: Any = root
            for part in ref[2:].split("/"):
                target = target[part]
            return _inline_refs(target, root)
        return {k: _inline_refs(v, root) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline_refs(v, root) for v in node]
    return node


def _assert_response_matches_openapi(
    *,
    method: str,
    path_template: str,
    status_code: int,
    payload: Any,
) -> None:
    """Validate ``payload`` against the OpenAPI schema for that operation.

    Parameters
    ----------
    method:
        HTTP verb, lowercased to match OpenAPI's key ("get", "post"…).
    path_template:
        The OpenAPI path template, e.g. ``"/api/v1/assets/{asset_id}"``.
        Note this is the **template**, not the substituted URL — the
        caller is responsible for passing the same template the route
        was registered under or the lookup raises ``KeyError`` with a
        message that lists the available paths.
    status_code:
        The HTTP status returned by the call. OpenAPI keys responses
        by status string (``"200"``, ``"422"``…), so we cast.
    payload:
        ``response.json()`` from the call.

    On schema violation the raised ``AssertionError`` lists every
    error with the JSON pointer to the offending node — copy-pasteable
    into a debug session.
    """
    try:
        paths = _OPENAPI_SCHEMA["paths"]
        operation = paths[path_template][method.lower()]
        raw_schema = operation["responses"][str(status_code)]["content"][
            "application/json"
        ]["schema"]
    except KeyError as exc:
        raise AssertionError(
            f"OpenAPI has no {method.upper()} {path_template} -> {status_code} "
            f"response schema (missing key: {exc.args[0]!r}). Either the path "
            "template is wrong, or the route does not declare a response "
            "for this status — see app/api/v1/endpoints/."
        ) from exc

    schema = _inline_refs(raw_schema, _OPENAPI_SCHEMA)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors:
        rendered = "\n".join(
            f"  - at {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in errors
        )
        raise AssertionError(
            f"{method.upper()} {path_template} -> {status_code} response "
            f"does not match its declared OpenAPI schema:\n{rendered}"
        )


class TestApiContract:
    """Contract drift checks across one endpoint per response shape we ship.

    Each test exercises a happy path or a documented error path and
    asserts the returned JSON matches the schema FastAPI advertises
    via ``/openapi.json``. Drift surfaces here as an explicit schema
    error message; without these tests, drift would only be caught
    when the frontend codegen or a downstream consumer broke.
    """

    def test_login_response_matches_schema(
        self,
        client: TestClient,
        make_user: Callable[..., User],
    ) -> None:
        # Setup: a holder we can log in as. Password matches make_user's default.
        holder = make_user(role=UserRole.HOLDER, email="contract-login@example.com")

        response = client.post(
            "/api/v1/auth/login",
            json={"email": holder.email, "password": "Password123"},
        )
        assert response.status_code == 200
        _assert_response_matches_openapi(
            method="post",
            path_template="/api/v1/auth/login",
            status_code=200,
            payload=response.json(),
        )

    def test_register_response_matches_schema(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "contract-register@example.com",
                "password": "Password123",
                "name": "Contract Tester",
                "department": "QA",
            },
        )
        assert response.status_code == 201
        _assert_response_matches_openapi(
            method="post",
            path_template="/api/v1/auth/register",
            status_code=201,
            payload=response.json(),
        )

    def test_list_assets_response_matches_schema(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        # A manager can list everything; a holder can too but with scoping.
        # The schema shape is the same — manager keeps the test simple.
        manager = make_user(role=UserRole.MANAGER, email="contract-list@example.com")

        response = client.get("/api/v1/assets", headers=auth_headers(manager))
        assert response.status_code == 200
        _assert_response_matches_openapi(
            method="get",
            path_template="/api/v1/assets",
            status_code=200,
            payload=response.json(),
        )

    def test_unauthorized_error_envelope_matches_schema(
        self,
        client: TestClient,
    ) -> None:
        """Anonymous calls to a protected endpoint must use the documented
        error envelope.

        The 401 body is produced by the global ``HTTPException`` handler
        in ``app/main.py``, not by ``response_model``. That makes it the
        most plausible drift source: a refactor that changed the handler
        to return ``{"detail": ...}`` (FastAPI's default) would leave
        every other test green and silently break every consumer that
        switches on ``body.error.code``.
        """
        response = client.get("/api/v1/assets")
        assert response.status_code == 401
        _assert_response_matches_openapi(
            method="get",
            path_template="/api/v1/assets",
            status_code=401,
            payload=response.json(),
        )

    def test_forbidden_error_envelope_matches_schema(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        """Wrong-role calls return the same envelope at 403.

        Pairs with the 401 test to confirm both error paths share one
        shape — the schema declares ``ErrorResponse`` for both, and a
        regression on either side would otherwise only surface at
        runtime via a frontend type-narrowing failure.
        """
        holder = make_user(role=UserRole.HOLDER, email="contract-forbidden@example.com")

        # POST /auth/users is manager-only (see auth.py: "Create a user of
        # any role (manager-only)"). A holder hitting it must get 403.
        response = client.post(
            "/api/v1/auth/users",
            headers=auth_headers(holder),
            json={
                "email": "newholder@example.com",
                "password": "Password123",
                "name": "X",
                "department": "Y",
                "role": "holder",
            },
        )
        assert response.status_code == 403
        _assert_response_matches_openapi(
            method="post",
            path_template="/api/v1/auth/users",
            status_code=403,
            payload=response.json(),
        )


# ---------------------------------------------------------------------------
# Multipart contract: POST /repair-requests
# ---------------------------------------------------------------------------
#
# The submit endpoint is the only multipart surface in the API and the
# highest-complexity contract we ship: the response embeds a list of
# uploaded images, each with a server-derived public URL that the
# frontend's image lightbox pins itself against. A regression that
# swaps that URL shape (e.g. dropping the ``/api/v1/`` prefix, or
# returning the raw storage key) would only surface as a broken
# image-not-found render in the UI — exactly the kind of integration
# bug the schema is supposed to defend against.
# ---------------------------------------------------------------------------


# Minimal JPEG: SOI + payload + EOI. The submit endpoint's
# ``_content_matches_declared_type`` checker reads the magic-byte
# prefix; the actual content is irrelevant.
_VALID_JPEG_BYTES = b"\xff\xd8api-contract-test-jpeg\xff\xd9"


def _seed_assigned_asset(db: Session, holder: User) -> Asset:
    """Create an in_use asset owned by ``holder`` so submit can succeed."""
    asset = Asset(
        asset_code=f"AST-CONTRACT-{uuid.uuid4().hex[:8]}",
        name="Contract test asset",
        model="X",
        category="computer",
        supplier="ACME",
        purchase_date=date(2026, 1, 1),
        purchase_amount=Decimal("100.00"),
        location="HQ",
        department="IT",
        status=AssetStatus.IN_USE,
        responsible_person_id=holder.id,
        assignment_date=date(2026, 2, 1),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


class _FailingImageStorage:
    """ImageStorage stub that always errors on save.

    Mirrors the version in ``test_repair_requests.py`` but is repeated
    here so the contract test stays self-contained — importing across
    test files creates a fragile dependency where deleting the helper
    in one file silently breaks the other.
    """

    def save(
        self,
        *,
        repair_request_id: str,
        image_id: str,
        suffix: str,
        content: bytes,
    ) -> str:
        raise ImageStorageError("contract test: simulated storage outage")

    def open(self, storage_key: str) -> tuple[bytes, str]:
        raise ImageStorageError("contract test: simulated storage outage")

    def cleanup(self, storage_keys: list[str]) -> None:
        return None


class TestRepairSubmitMultipartContract:
    """Validate the multipart submit endpoint's response shape against OpenAPI.

    Covered:
    - **Happy path (201)** — image successfully uploaded, response includes
      the image list with the contract's `id` + `url` shape.
    - **Storage failure (503)** — the global error envelope is correctly
      emitted when ``ImageStorage.save`` raises. The 503 path is owned
      by ``app/main.py``'s ``HTTPException`` handler (one level above
      ``response_model``), so this is exactly the kind of cell that
      drift can sneak past every other test.
    """

    def test_multipart_submit_response_matches_schema(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER, email="contract-submit@example.com")
        asset = _seed_assigned_asset(db_session, holder)

        response = client.post(
            "/api/v1/repair-requests",
            data={
                "asset_id": asset.id,
                "fault_description": "Screen flicker (contract test).",
            },
            files=[("images", ("issue.jpg", _VALID_JPEG_BYTES, "image/jpeg"))],
            headers=auth_headers(holder),
        )

        assert response.status_code == 201, response.text
        # The frontend lightbox pins itself against the documented URL
        # shape. A regression that drops the prefix would only surface
        # downstream as a broken image render — assert it inline here.
        images = response.json()["data"]["images"]
        assert len(images) == 1
        assert images[0]["url"] == f"/api/v1/images/{images[0]['id']}"

        _assert_response_matches_openapi(
            method="post",
            path_template="/api/v1/repair-requests",
            status_code=201,
            payload=response.json(),
        )

    def test_storage_failure_error_envelope_matches_schema(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
    ) -> None:
        holder = make_user(role=UserRole.HOLDER, email="contract-503@example.com")
        asset = _seed_assigned_asset(db_session, holder)

        # ``client`` fixture's teardown calls ``app.dependency_overrides.clear()``
        # which removes ALL overrides — including ``get_db``. The next test's
        # ``client`` fixture invocation re-adds the ``get_db`` override on
        # entry, so the per-test isolation still holds. The override added
        # here is therefore rolled back before any other test runs.
        app.dependency_overrides[get_image_storage] = lambda: _FailingImageStorage()

        response = client.post(
            "/api/v1/repair-requests",
            data={
                "asset_id": asset.id,
                "fault_description": "Screen flicker (storage-fail test).",
            },
            files=[("images", ("issue.jpg", _VALID_JPEG_BYTES, "image/jpeg"))],
            headers=auth_headers(holder),
        )

        assert response.status_code == 503, response.text
        _assert_response_matches_openapi(
            method="post",
            path_template="/api/v1/repair-requests",
            status_code=503,
            payload=response.json(),
        )


class TestRefInlineHelper:
    """Sanity checks for ``_inline_refs`` itself.

    Without these, a regression in the helper would silently turn
    every contract test into a no-op (the validator would happily
    accept ``{"$ref": ...}`` as just an opaque dict). Keep the helper
    honest with two micro-tests.
    """

    def test_replaces_single_ref(self) -> None:
        root = {"components": {"schemas": {"Foo": {"type": "object", "required": ["a"]}}}}
        resolved = _inline_refs({"$ref": "#/components/schemas/Foo"}, root)
        assert resolved == {"type": "object", "required": ["a"]}

    def test_rejects_non_local_ref(self) -> None:
        with pytest.raises(ValueError, match="Only local refs supported"):
            _inline_refs({"$ref": "http://example.com/schema.json"}, {})
