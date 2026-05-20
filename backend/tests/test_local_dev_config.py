"""Local development configuration contract tests."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_docker_compose_backend_explicitly_loads_backend_env_file() -> None:
    """Option A should fail early if ``backend/.env`` has not been created.

    Bootstrap credentials are now required. The Docker quick-start path should
    make the env-file dependency explicit instead of relying only on the app
    discovering ``/app/.env`` through the bind mount.
    """
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "env_file:" in compose
    assert "- ./backend/.env" in compose
