"""Verify the demo-seed script includes the bootstrap manager (Decision A2)."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.security import verify_password
from app.models.user import UserRole
from scripts.seed_demo_data import build_bootstrap_manager, build_users


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
