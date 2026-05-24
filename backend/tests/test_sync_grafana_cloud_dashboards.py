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


def test_main_requires_stack_url_when_not_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing --stack-url in live mode exits non-zero with a clear error."""
    _write_dashboard(tmp_path, "ams-x", "X")
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "test-token")

    with pytest.raises(SystemExit) as excinfo:
        sync_module.main(["--dashboards-dir", str(tmp_path)])

    assert excinfo.value.code != 0


def test_main_missing_dashboards_dir_returns_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pointing at a non-existent directory must surface as a clean failure.

    The runbook is invoked from operator laptops; a typo in
    ``--dashboards-dir`` should fail loud, not look like a successful
    no-op of "zero dashboards published".
    """
    nonexistent = tmp_path / "does-not-exist"

    exit_code = sync_module.main(
        ["--dashboards-dir", str(nonexistent), "--dry-run"]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "not found" in captured.err.lower()


def test_main_empty_dashboards_dir_returns_1(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty directory exits 1 with a clear "no dashboards" message."""
    exit_code = sync_module.main(
        ["--dashboards-dir", str(tmp_path), "--dry-run"]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "no dashboards" in captured.err.lower()


def test_main_partial_publish_failure_exits_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One dashboard failing among many surfaces as a non-zero exit code.

    A partial-publish failure must not be swallowed silently — the GC
    stack would otherwise be left with a mix of new and stale dashboard
    schemas. Two dashboards, second returns 403 (insufficient scope on
    the API key); main() reports exit 1.
    """
    _write_dashboard(tmp_path, "ams-ok", "OK")
    _write_dashboard(tmp_path, "ams-bad", "Bad")
    mock_post = MagicMock(side_effect=[200, 403])
    monkeypatch.setattr(sync_module, "post_dashboard", mock_post)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "test-token")

    exit_code = sync_module.main(
        ["--dashboards-dir", str(tmp_path), "--stack-url", "https://x.grafana.net"]
    )

    assert exit_code == 1
    assert mock_post.call_count == 2


def test_main_3xx_redirect_is_treated_as_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 302 (e.g. GC redirecting an under-scoped POST to its login page)
    must NOT be silently counted as success."""
    _write_dashboard(tmp_path, "ams-redirect", "Redirect")
    mock_post = MagicMock(return_value=302)
    monkeypatch.setattr(sync_module, "post_dashboard", mock_post)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "test-token")

    exit_code = sync_module.main(
        ["--dashboards-dir", str(tmp_path), "--stack-url", "https://x.grafana.net"]
    )

    assert exit_code == 1


def test_post_dashboard_catches_url_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A DNS/connection failure must surface as 599 (and a stderr message)
    rather than crashing the loop.

    A network blip while publishing dashboard #3 of 6 would otherwise
    abort the loop with an uncaught URLError, leaving dashboards #4-6
    referencing the Phase-2 metric schema. Patches the script's
    custom no-redirect opener (not module-level urlopen) because the
    post_dashboard refactor routes through ``_NO_REDIRECT_OPENER.open``.
    """
    import urllib.error

    def _raise_url_error(*_args: Any, **_kwargs: Any) -> Any:
        raise urllib.error.URLError("connection refused")

    mock_opener = MagicMock()
    mock_opener.open = _raise_url_error
    monkeypatch.setattr(sync_module, "_NO_REDIRECT_OPENER", mock_opener)

    status = sync_module.post_dashboard(
        "https://x.grafana.net", "tok", {"dashboard": {"uid": "ams-net-fail"}}
    )

    assert status == 599


def test_post_dashboard_returns_3xx_status_on_redirect(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A 3xx response from GC must be surfaced as the raw status code.

    Without the no-redirect handler urllib would follow the redirect
    (typically to an SSO login page that returns 200), masking the
    auth-scope problem. ``_NoRedirectHandler`` converts every 3xx into
    an ``HTTPError`` so ``post_dashboard``'s exception arm runs and
    the operator-facing FAIL line carries both the code and the
    "missing dashboards-write scope" hint.
    """
    import urllib.error

    def _raise_redirect(*_args: Any, **_kwargs: Any) -> Any:
        raise urllib.error.HTTPError(
            url="https://x.grafana.net/api/dashboards/db",
            code=302,
            msg="Found",
            hdrs={},  # type: ignore[arg-type]
            fp=None,
        )

    mock_opener = MagicMock()
    mock_opener.open = _raise_redirect
    monkeypatch.setattr(sync_module, "_NO_REDIRECT_OPENER", mock_opener)

    status = sync_module.post_dashboard(
        "https://x.grafana.net", "tok", {"dashboard": {"uid": "ams-3xx"}}
    )

    assert status == 302
    captured = capsys.readouterr()
    assert "FAIL" in captured.err
    assert "ams-3xx" in captured.err
    assert "302" in captured.err
    # Hint about API-key scope must appear so operators recognise the symptom.
    assert "dashboards-write scope" in captured.err


def test_main_double_run_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Running main() twice in a row against the same dashboards must
    both succeed: the GC dashboards-DB endpoint upserts by uid and the
    script wraps every payload with ``overwrite: true``. A regression
    that, say, switched to ``overwrite: false`` would surface as a 412
    or 409 on the second run; this test would fail loud.
    """
    _write_dashboard(tmp_path, "ams-a", "A")
    _write_dashboard(tmp_path, "ams-b", "B")
    mock_post = MagicMock(return_value=200)
    monkeypatch.setattr(sync_module, "post_dashboard", mock_post)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "test-token")

    argv = [
        "--dashboards-dir",
        str(tmp_path),
        "--stack-url",
        "https://x.grafana.net",
    ]

    first_exit = sync_module.main(argv)
    second_exit = sync_module.main(argv)

    assert first_exit == 0
    assert second_exit == 0
    # Each run posts both dashboards; the second run still passes
    # ``overwrite: true`` in build_payload, so the API call shape is
    # identical and GC's upsert keeps both dashboards live.
    assert mock_post.call_count == 4

    # All four calls must carry the overwrite=True envelope so the
    # second run is provably an upsert, not a create-only.
    for call in mock_post.call_args_list:
        payload = next(
            v for v in (*call.args, *call.kwargs.values()) if isinstance(v, dict)
        )
        assert payload.get("overwrite") is True, payload

    out = capsys.readouterr().out
    # Final summary line appears once per run.
    assert out.count("published successfully") == 2


def test_main_partial_failure_prints_summary_with_uids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The final summary on partial failure lists exactly which uids
    failed, so the operator doesn't have to scroll the CI log to count
    individual FAIL lines. UIDs are deliberately ordered so that
    ``load_dashboards`` (which sorts alphabetically) matches the
    side_effect ordering on the mock: ams-1-ok → 200, ams-2-bad → 403,
    ams-3-bad → 599.
    """
    _write_dashboard(tmp_path, "ams-1-ok", "OK")
    _write_dashboard(tmp_path, "ams-2-bad", "Bad 1")
    _write_dashboard(tmp_path, "ams-3-bad", "Bad 2")
    mock_post = MagicMock(side_effect=[200, 403, 599])
    monkeypatch.setattr(sync_module, "post_dashboard", mock_post)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "test-token")

    exit_code = sync_module.main(
        ["--dashboards-dir", str(tmp_path), "--stack-url", "https://x.grafana.net"]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "2 of 3 dashboard" in err
    assert "ams-2-bad" in err
    assert "ams-3-bad" in err
    # The successful uid must NOT appear in the failure summary.
    assert "ams-1-ok" not in err


def test_main_aborts_on_consecutive_transport_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two consecutive 599 (URLError) returns from post_dashboard must
    short-circuit the loop and report the unattempted dashboards as
    skipped.

    Without this fail-fast, a network outage against GC would produce
    ``len(dashboards) * HTTP_TIMEOUT_SECONDS`` of CI hang (6 × 30 s =
    3 min today, scaling with the dashboard count). The operator should
    see the failure summary immediately. HTTPError-class failures
    (4xx/5xx) do NOT trip the abort because they imply GC is reachable
    and the issue is request-level.
    """
    _write_dashboard(tmp_path, "ams-1", "First")
    _write_dashboard(tmp_path, "ams-2", "Second")
    _write_dashboard(tmp_path, "ams-3", "Third")
    _write_dashboard(tmp_path, "ams-4", "Fourth")
    # First two are 599 (transport failure); after the second the loop
    # aborts and the remaining two are never attempted.
    mock_post = MagicMock(side_effect=[599, 599])
    monkeypatch.setattr(sync_module, "post_dashboard", mock_post)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "test-token")

    exit_code = sync_module.main(
        ["--dashboards-dir", str(tmp_path), "--stack-url", "https://x.grafana.net"]
    )

    assert exit_code == 1
    # Only two posts were attempted; the rest were skipped on abort.
    assert mock_post.call_count == 2, mock_post.call_args_list
    err = capsys.readouterr().err
    assert "ABORT" in err
    assert "consecutive transport failures" in err
    # Summary mentions all four uids — two failed, two skipped after abort.
    assert "4 of 4 dashboard" in err
    assert "2 skipped after abort" in err
    for uid in ("ams-1", "ams-2", "ams-3", "ams-4"):
        assert uid in err, uid


def test_main_does_not_abort_on_consecutive_http_4xx_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two consecutive 4xx returns must NOT trigger the abort.

    A 4xx implies the API key is reachable but lacks scope, or the
    payload is malformed — the operator wants the full per-dashboard
    error list, not an early abort masking some of the failures.
    """
    _write_dashboard(tmp_path, "ams-1", "First")
    _write_dashboard(tmp_path, "ams-2", "Second")
    _write_dashboard(tmp_path, "ams-3", "Third")
    mock_post = MagicMock(side_effect=[403, 403, 403])
    monkeypatch.setattr(sync_module, "post_dashboard", mock_post)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "test-token")

    exit_code = sync_module.main(
        ["--dashboards-dir", str(tmp_path), "--stack-url", "https://x.grafana.net"]
    )

    assert exit_code == 1
    # All three should have been attempted.
    assert mock_post.call_count == 3
    err = capsys.readouterr().err
    assert "ABORT" not in err
    assert "3 of 3 dashboard" in err


def test_default_dashboards_dir_is_anchored_on_file(
) -> None:
    """``DEFAULT_DASHBOARDS_DIR`` resolves relative to the script's location,
    not the caller's CWD — so the runbook command works from any directory."""
    expected_suffix = Path("config") / "grafana" / "dashboards"
    assert str(sync_module.DEFAULT_DASHBOARDS_DIR).endswith(str(expected_suffix))
    # Must be absolute (would be relative if anchored on CWD).
    assert sync_module.DEFAULT_DASHBOARDS_DIR.is_absolute()


def test_no_redirect_handler_blocks_real_3xx_on_post(
    tmp_path: Path,
) -> None:
    """Integration test: a real HTTP server returning 302 on POST must
    surface as HTTPError, NOT be silently followed.

    The unit-level test for ``_NoRedirectHandler`` mocks ``opener.open``
    and asserts the right exception type. That proves the dispatch
    *given* a 3xx, but it doesn't prove that urllib's HTTP path
    actually invokes ``_NoRedirectHandler.http_error_302`` for a real
    response. This test stands up a stdlib ``http.server.HTTPServer``
    that replies 302 to every POST, then asks ``post_dashboard`` to
    publish against it — the only thing that can stop urllib from
    silently following the redirect is ``_NoRedirectHandler``. A
    regression that removed the handler would fail here even though
    the unit test still passed.
    """
    import http.server
    import threading

    class RedirectingHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(302)
            self.send_header("Location", "/auth/login")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            # Silence the default per-request stderr noise.
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), RedirectingHandler)
    host, port = server.server_address[:2]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status = sync_module.post_dashboard(
            f"http://{host}:{port}",
            "fake-api-key",
            sync_module.build_payload({"uid": "ams-test", "title": "Test"}),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    # The real 302 from the stdlib server must propagate as the
    # response code, NOT be silently followed to a 404 / 200 / etc.
    assert status == 302, status

