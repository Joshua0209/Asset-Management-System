from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetStatus
from app.models.repair_image import RepairImage
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole

_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-payload"
_JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-payload"


def _seed_repair_request(session: Session, holder: User) -> RepairRequest:
    asset = Asset(
        asset_code="AST-2026-00099",
        name="Imaging Test Laptop",
        model="Test Model",
        category="computer",
        supplier="Vendor",
        purchase_date=date(2026, 1, 1),
        purchase_amount=Decimal("1000.00"),
        location="HQ",
        department="IT",
        status=AssetStatus.PENDING_REPAIR,
        responsible_person_id=holder.id,
    )
    session.add(asset)
    session.flush()
    rr = RepairRequest(
        asset_id=asset.id,
        repair_id="REP-2026-90001",
        requester_id=holder.id,
        status=RepairRequestStatus.PENDING_REVIEW,
        fault_description="Image fixture",
    )
    session.add(rr)
    session.flush()
    return rr


def _attach_image(
    session: Session,
    *,
    rr: RepairRequest,
    upload_dir: Path,
    suffix: str,
    content: bytes,
) -> RepairImage:
    image_id = str(uuid4())
    storage_key = f"{rr.id}/{image_id}{suffix}"
    target = upload_dir / storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    image = RepairImage(
        id=image_id,
        repair_request_id=rr.id,
        image_url=storage_key,
        uploaded_at=datetime.now(UTC),
    )
    session.add(image)
    session.flush()
    return image


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """Point the storage backend at a per-test temp dir.

    Overrides ``REPAIR_UPLOAD_DIR`` and clears the cached settings so the
    storage dependency picks up the new path for this test only. ``monkeypatch``
    restores the env var on teardown; we clear the cache afterwards so other
    tests rebuild ``Settings`` against the restored value.
    """
    monkeypatch.setenv("REPAIR_UPLOAD_DIR", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        yield tmp_path
    finally:
        get_settings.cache_clear()


class TestGetImage:
    def test_returns_png_bytes_to_authenticated_holder(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        upload_dir: Path,
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        rr = _seed_repair_request(db_session, holder)
        image = _attach_image(
            db_session, rr=rr, upload_dir=upload_dir, suffix=".png", content=_PNG_BYTES
        )
        db_session.commit()

        response = client.get(
            f"/api/v1/images/{image.id}",
            headers=auth_headers(holder),
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content == _PNG_BYTES

    def test_jpeg_returns_jpeg_content_type(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        upload_dir: Path,
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        rr = _seed_repair_request(db_session, holder)
        image = _attach_image(
            db_session, rr=rr, upload_dir=upload_dir, suffix=".jpg", content=_JPEG_BYTES
        )
        db_session.commit()

        response = client.get(
            f"/api/v1/images/{image.id}",
            headers=auth_headers(holder),
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content == _JPEG_BYTES

    def test_manager_can_view_other_users_images(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        upload_dir: Path,
    ) -> None:
        # FR-31: any authenticated user can view repair-request images.
        holder = make_user(role=UserRole.HOLDER)
        manager = make_user(role=UserRole.MANAGER)
        rr = _seed_repair_request(db_session, holder)
        image = _attach_image(
            db_session, rr=rr, upload_dir=upload_dir, suffix=".png", content=_PNG_BYTES
        )
        db_session.commit()

        response = client.get(
            f"/api/v1/images/{image.id}",
            headers=auth_headers(manager),
        )

        assert response.status_code == 200
        assert response.content == _PNG_BYTES

    def test_other_holder_can_view_image_per_fr31(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        upload_dir: Path,
    ) -> None:
        owner = make_user(role=UserRole.HOLDER, email="owner@example.com")
        other = make_user(role=UserRole.HOLDER, email="other@example.com")
        rr = _seed_repair_request(db_session, owner)
        image = _attach_image(
            db_session, rr=rr, upload_dir=upload_dir, suffix=".png", content=_PNG_BYTES
        )
        db_session.commit()

        response = client.get(
            f"/api/v1/images/{image.id}",
            headers=auth_headers(other),
        )

        assert response.status_code == 200

    def test_unauthenticated_returns_401(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        upload_dir: Path,
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        rr = _seed_repair_request(db_session, holder)
        image = _attach_image(
            db_session, rr=rr, upload_dir=upload_dir, suffix=".png", content=_PNG_BYTES
        )
        db_session.commit()

        response = client.get(f"/api/v1/images/{image.id}")

        assert response.status_code == 401

    def test_unknown_image_id_returns_404(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        upload_dir: Path,
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)

        response = client.get(
            "/api/v1/images/00000000-0000-0000-0000-000000000000",
            headers=auth_headers(holder),
        )

        assert response.status_code == 404

    def test_soft_deleted_repair_request_hides_image(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        upload_dir: Path,
    ) -> None:
        holder = make_user(role=UserRole.HOLDER)
        rr = _seed_repair_request(db_session, holder)
        image = _attach_image(
            db_session, rr=rr, upload_dir=upload_dir, suffix=".png", content=_PNG_BYTES
        )
        rr.deleted_at = datetime.now(UTC)
        db_session.commit()

        response = client.get(
            f"/api/v1/images/{image.id}",
            headers=auth_headers(holder),
        )

        assert response.status_code == 404

    def test_missing_file_on_disk_returns_404(
        self,
        client: TestClient,
        db_session: Session,
        make_user: Callable[..., User],
        auth_headers: Callable[[User], dict[str, str]],
        upload_dir: Path,
    ) -> None:
        # DB row exists but the underlying file was wiped (e.g., disk lost).
        holder = make_user(role=UserRole.HOLDER)
        rr = _seed_repair_request(db_session, holder)
        image = _attach_image(
            db_session, rr=rr, upload_dir=upload_dir, suffix=".png", content=_PNG_BYTES
        )
        (upload_dir / image.image_url).unlink()
        db_session.commit()

        response = client.get(
            f"/api/v1/images/{image.id}",
            headers=auth_headers(holder),
        )

        # ImageNotFoundError → 404 via image_storage_error_to_http.
        assert response.status_code == 404
