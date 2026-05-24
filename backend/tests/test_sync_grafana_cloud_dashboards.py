"""Unit tests for the one-shot dashboards sync script.

Phase 4 of `docs/plans/observability-prod-migration-plan.md`. The script
lives at the repo root (`scripts/sync_grafana_cloud_dashboards.py`) and
is run from there; this test inserts its parent directory into `sys.path`
so the module can be imported in-process.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

sync_module = pytest.importorskip(
    "sync_grafana_cloud_dashboards",
    reason="Phase 4 sync script not yet implemented",
)


def _write_dashboard(tmp_path: Path, uid: str, title: str) -> Path:
    path = tmp_path / f"{uid}.json"
    path.write_text(json.dumps({"uid": uid, "title": title, "panels": []}))
    return path


def test_load_dashboards_reads_all_json_files(tmp_path: Path) -> None:
    _write_dashboard(tmp_path, "ams-a", "A")
    _write_dashboard(tmp_path, "ams-b", "B")
    (tmp_path / "not-a-dashboard.txt").write_text("ignore me")

    loaded = sync_module.load_dashboards(tmp_path)

    assert len(loaded) == 2
    uids = {d["uid"] for d in loaded}
    assert uids == {"ams-a", "ams-b"}


def test_load_dashboards_raises_on_missing_uid(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text(json.dumps({"title": "no uid"}))

    with pytest.raises(ValueError, match="uid"):
        sync_module.load_dashboards(tmp_path)


def test_build_payload_wraps_dashboard_with_overwrite_true() -> None:
    dashboard = {"uid": "ams-x", "title": "X"}

    payload = sync_module.build_payload(dashboard)

    assert payload == {"dashboard": dashboard, "overwrite": True}


def test_main_dry_run_loads_but_does_not_post(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_dashboard(tmp_path, "ams-dry", "Dry")
    mock_post = MagicMock()
    monkeypatch.setattr(sync_module, "post_dashboard", mock_post)

    exit_code = sync_module.main(
        ["--dashboards-dir", str(tmp_path), "--dry-run"]
    )

    assert exit_code == 0
    mock_post.assert_not_called()
    captured = capsys.readouterr()
    assert "ams-dry" in captured.out
    assert "dry run" in captured.out.lower()


def test_main_live_run_posts_each_dashboard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_dashboard(tmp_path, "ams-1", "One")
    _write_dashboard(tmp_path, "ams-2", "Two")
    mock_post = MagicMock(return_value=200)
    monkeypatch.setattr(sync_module, "post_dashboard", mock_post)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "test-token")

    exit_code = sync_module.main(
        ["--dashboards-dir", str(tmp_path), "--stack-url", "https://x.grafana.net"]
    )

    assert exit_code == 0
    assert mock_post.call_count == 2
    for call in mock_post.call_args_list:
        kwargs = dict(call.kwargs) if call.kwargs else {}
        args = call.args
        all_values: list[Any] = [*args, *kwargs.values()]
        assert any("https://x.grafana.net" in str(v) for v in all_values)
        assert any("test-token" in str(v) for v in all_values)


def test_main_requires_api_key_when_not_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_dashboard(tmp_path, "ams-x", "X")
    monkeypatch.delenv("GRAFANA_CLOUD_API_KEY", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        sync_module.main(
            ["--dashboards-dir", str(tmp_path), "--stack-url", "https://x.grafana.net"]
        )

    assert excinfo.value.code != 0
