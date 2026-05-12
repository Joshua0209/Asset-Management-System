"""Guard against the seed-script regression where importing a subset of models
left SQLAlchemy unable to resolve string relationship references (issue #47).

These tests must run in a fresh Python subprocess. The test suite's
``conftest.py`` eagerly imports every model module for side effects, which
masks the bug: once any test process has imported ``asset_action_history``
once, the registry is populated for the rest of the session. A subprocess
gives us a clean import state that mirrors what ``scripts/seed_demo_data.py``
actually sees when run via ``docker compose run``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _run_in_subprocess(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class TestModelsPackageRegistersAllMappers:
    def test_importing_asset_alone_resolves_action_history_relationship(self) -> None:
        result = _run_in_subprocess(
            """
            from app.models.asset import Asset  # noqa: F401
            from sqlalchemy.orm import configure_mappers
            configure_mappers()
            print("ok")
            """
        )
        assert result.returncode == 0, (
            "Importing app.models.asset must register every related mapper. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "ok"

    def test_seed_script_module_import_does_not_raise(self) -> None:
        result = _run_in_subprocess(
            """
            import scripts.seed_demo_data  # noqa: F401
            from sqlalchemy.orm import configure_mappers
            configure_mappers()
            print("ok")
            """
        )
        assert result.returncode == 0, (
            "Importing scripts.seed_demo_data and configuring mappers must "
            "succeed without InvalidRequestError. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "ok"

    @pytest.mark.parametrize(
        "submodule",
        [
            "asset",
            "asset_action_history",
            "repair_image",
            "repair_request",
            "user",
        ],
    )
    def test_any_single_submodule_import_resolves_all_mappers(
        self, submodule: str
    ) -> None:
        """Whichever model the caller imports first, every relationship —
        including ``Asset.action_histories`` — must resolve."""
        result = _run_in_subprocess(
            f"""
            import importlib
            importlib.import_module("app.models.{submodule}")
            from sqlalchemy.orm import configure_mappers
            configure_mappers()
            print("ok")
            """
        )
        assert result.returncode == 0, (
            f"Importing app.models.{submodule} alone must register every mapper. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
