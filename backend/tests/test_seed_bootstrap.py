"""Verify the demo-seed script includes the bootstrap manager (Decision A2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.security import verify_password
from app.models.repair_request import RepairRequest
from app.models.user import UserRole
from scripts.seed_demo_data import build_bootstrap_manager, build_images, build_users


class TestBootstrapManager:
    def test_build_bootstrap_manager_matches_settings(self) -> None:
        settings = get_settings()
        user = build_bootstrap_manager()
        assert user.email == settings.bootstrap_manager_email
        assert user.role is UserRole.MANAGER
        assert user.name == settings.bootstrap_manager_name
        assert user.department == settings.bootstrap_manager_department
        # Password is stored hashed, verifies against the configured plaintext.
        assert verify_password(settings.bootstrap_manager_password, user.password_hash)

    def test_build_users_contains_bootstrap_manager(self) -> None:
        settings = get_settings()
        users = build_users()
        emails = {u.email for u in users}
        assert settings.bootstrap_manager_email in emails


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
