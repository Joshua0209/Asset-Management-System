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

    loaded, malformed = sync_module.load_dashboards(tmp_path)

    assert len(loaded) == 2
    assert malformed == []
    uids = {d["uid"] for d in loaded}
    assert uids == {"ams-a", "ams-b"}


def test_load_dashboards_reports_missing_uid_as_malformed(tmp_path: Path) -> None:
    """A dashboard missing ``uid`` is recorded as malformed, not raised.

    Per the HIGH review finding: aborting load_dashboards with an
    uncaught exception means valid dashboards earlier in iteration
    order are dropped on the floor without a summary line. The fix
    routes invalid files through the same ``malformed`` list that
    ``main()`` surfaces alongside publish failures.
    """
    _write_dashboard(tmp_path, "ams-ok", "Valid")
    (tmp_path / "broken.json").write_text(json.dumps({"title": "no uid"}))

    loaded, malformed = sync_module.load_dashboards(tmp_path)

    assert len(loaded) == 1
    assert loaded[0]["uid"] == "ams-ok"
    assert malformed == ["broken.json"]


def test_load_dashboards_reports_malformed_json_as_malformed(
    tmp_path: Path,
) -> None:
    """Invalid JSON in one file does NOT abort the whole load with a
    raw stacktrace; the file is reported as malformed and the others
    continue."""
    _write_dashboard(tmp_path, "ams-good", "OK")
    (tmp_path / "ams-bad.json").write_text("{ not valid json")

    loaded, malformed = sync_module.load_dashboards(tmp_path)

    assert len(loaded) == 1
    assert loaded[0]["uid"] == "ams-good"
    assert malformed == ["ams-bad.json"]


def test_main_dry_run_returns_1_when_any_dashboard_malformed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--dry-run`` is the CI validate gate; one malformed file must
    fail the gate so the bad JSON never reaches the production sync."""
    _write_dashboard(tmp_path, "ams-ok", "OK")
    (tmp_path / "ams-bad.json").write_text("{ broken")

    exit_code = sync_module.main(
        ["--dashboards-dir", str(tmp_path), "--dry-run"]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "malformed" in err
    assert "ams-bad.json" in err


def test_main_live_run_surfaces_malformed_in_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """In live mode, malformed files appear in the final failure
    summary alongside publish failures, and the script exits non-zero."""
    _write_dashboard(tmp_path, "ams-ok", "OK")
    (tmp_path / "ams-bad.json").write_text("{ not json")
    mock_post = MagicMock(return_value=200)
    monkeypatch.setattr(sync_module, "post_dashboard", mock_post)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "test-token")

    exit_code = sync_module.main(
        ["--dashboards-dir", str(tmp_path), "--stack-url", "https://x.grafana.net"]
    )

    assert exit_code == 1
    # The valid dashboard was still posted (graceful degradation).
    assert mock_post.call_count == 1
    err = capsys.readouterr().err
    assert "1 of 2 dashboard" in err
    assert "1 malformed" in err
    assert "ams-bad.json" in err


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


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://x.grafana.net",
        "http://169.254.169.254/latest",  # AWS EC2 metadata service
        "ftp://x.grafana.net",
        "file:///etc/passwd",
        "ldap://internal/",
        "x.grafana.net",  # scheme omitted entirely
    ],
)
def test_main_rejects_non_https_stack_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    bad_url: str,
) -> None:
    """M3 contract: only https:// stack URLs are accepted in live mode.

    The bearer token (``GRAFANA_CLOUD_API_KEY``) is added to every
    request. A mistyped or env-driven plaintext URL would send the
    token over the wire unprotected, or to the EC2 IMDS metadata
    endpoint, or to any other unintended target. Fail closed BEFORE
    any HTTP request is issued.
    """
    _write_dashboard(tmp_path, "ams-x", "X")
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "secret-token-do-not-leak")

    with pytest.raises(SystemExit) as excinfo:
        sync_module.main(
            ["--dashboards-dir", str(tmp_path), "--stack-url", bad_url]
        )

    assert excinfo.value.code != 0
    captured = capsys.readouterr()
    assert "https://" in captured.err
    # The credential MUST NOT appear in the error message (defensive: a
    # future refactor that interpolated args without sanitization would
    # leak the token to the operator's terminal).
    assert "secret-token-do-not-leak" not in captured.err


def test_main_missing_dashboards_dir_returns_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pointing at a non-existent directory with the dashboards target
    explicit must surface as a clean failure.

    The runbook is invoked from operator laptops; a typo in
    ``--dashboards-dir`` should fail loud, not look like a successful
    no-op of "zero dashboards published". Passes ``--targets dashboards``
    explicitly because the new default (``all``) intentionally
    soft-skips a missing dashboards dir so the alerts pass can run on
    its own — that soft-skip path is covered by the alerts-side tests.
    """
    nonexistent = tmp_path / "does-not-exist"

    exit_code = sync_module.main(
        [
            "--targets",
            "dashboards",
            "--dashboards-dir",
            str(nonexistent),
            "--dry-run",
        ]
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
    """N consecutive 599 (URLError) returns from post_dashboard must
    short-circuit the loop and report the unattempted dashboards as
    skipped. N matches ``_CONSECUTIVE_TRANSPORT_FAIL_LIMIT``.

    Without this fail-fast, a network outage against GC would produce
    ``len(dashboards) * HTTP_TIMEOUT_SECONDS`` of CI hang (6 × 30 s =
    3 min today, scaling with the dashboard count). The operator should
    see the failure summary at the threshold rather than after a long
    CI hang. HTTPError-class failures (4xx/5xx) do NOT trip the abort
    because they imply GC is reachable and the issue is request-level.
    """
    limit = sync_module._CONSECUTIVE_TRANSPORT_FAIL_LIMIT
    # Need enough dashboards to surface the post-abort skip behavior.
    total_dashboards = limit + 2
    for i in range(1, total_dashboards + 1):
        _write_dashboard(tmp_path, f"ams-{i}", f"#{i}")
    # First ``limit`` are 599 (transport failure); after the limit-th
    # the loop aborts and the remaining dashboards are never attempted.
    mock_post = MagicMock(side_effect=[599] * limit)
    monkeypatch.setattr(sync_module, "post_dashboard", mock_post)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "test-token")

    exit_code = sync_module.main(
        ["--dashboards-dir", str(tmp_path), "--stack-url", "https://x.grafana.net"]
    )

    assert exit_code == 1
    # Only ``limit`` posts were attempted; the rest were skipped on abort.
    assert mock_post.call_count == limit, mock_post.call_args_list
    err = capsys.readouterr().err
    assert "ABORT" in err
    assert "consecutive transport failures" in err
    skipped = total_dashboards - limit
    assert f"{total_dashboards} of {total_dashboards} dashboard" in err
    assert f"{skipped} skipped after abort" in err
    for i in range(1, total_dashboards + 1):
        assert f"ams-{i}" in err, f"ams-{i}"


def test_main_isolated_transport_blip_does_not_abort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An isolated 599 followed by a success must NOT trip the abort.

    Pins the L3 contract: the threshold-N fail-fast is for genuine
    outage detection, not for any single transient. The counter
    must reset on the first non-599 status so a network blip in
    the middle of an otherwise-healthy sync doesn't cause a false
    abort.

    Pattern is built from ``_CONSECUTIVE_TRANSPORT_FAIL_LIMIT`` so
    the test tracks the threshold automatically: ``(limit-1)`` 599s,
    one 200 (resets counter), ``(limit-1)`` 599s, one 200 (resets).
    A future threshold change flows through without rewriting the
    pattern, and the assertion still proves "every 599 reset by a
    200 leaves the counter below the abort line".
    """
    limit = sync_module._CONSECUTIVE_TRANSPORT_FAIL_LIMIT
    pattern = ([599] * (limit - 1) + [200]) * 2
    dashboard_count = len(pattern)
    for i in range(1, dashboard_count + 1):
        _write_dashboard(tmp_path, f"ams-{i}", f"Dashboard {i}")
    mock_post = MagicMock(side_effect=pattern)
    monkeypatch.setattr(sync_module, "post_dashboard", mock_post)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "test-token")

    exit_code = sync_module.main(
        ["--dashboards-dir", str(tmp_path), "--stack-url", "https://x.grafana.net"]
    )

    # Mix of failures + successes -> non-zero exit, but ABORT must not appear.
    assert exit_code == 1
    assert mock_post.call_count == dashboard_count, mock_post.call_args_list
    err = capsys.readouterr().err
    assert "ABORT" not in err, err


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


# ---------------------------------------------------------------------------
# Datasource UID remap
# ---------------------------------------------------------------------------


def test_collect_placeholder_uids_walks_panels_and_templating() -> None:
    """``collect_placeholder_uids`` returns every placeholder UID referenced.

    The traversal must cover panels, nested targets, templating
    variables, and annotations — anywhere Grafana puts a ``datasource``
    block. A missed location means a placeholder slips through without
    being remapped and the panel silently shows no data in GC.
    """
    dashboard = {
        "uid": "ams-x",
        "panels": [
            {
                "datasource": {"type": "prometheus", "uid": "prometheus"},
                "targets": [
                    {"datasource": {"type": "loki", "uid": "loki"}},
                ],
            },
            {"datasource": {"type": "cloudwatch", "uid": "cloudwatch"}},
        ],
        "templating": {
            "list": [
                {"datasource": {"type": "tempo", "uid": "tempo"}},
            ],
        },
        "annotations": {
            "list": [
                {"datasource": {"type": "pyroscope", "uid": "pyroscope"}},
            ],
        },
    }

    found = sync_module.collect_placeholder_uids(dashboard)

    assert found == {"prometheus", "loki", "cloudwatch", "tempo", "pyroscope"}


def test_collect_placeholder_uids_ignores_builtin_grafana_uid() -> None:
    """The Grafana built-in datasource ``uid="grafana"`` must NOT be remapped.

    Every Grafana instance has a built-in datasource with literal
    ``uid="grafana"`` for the default annotations source. Remapping it
    would point those annotations at nothing.
    """
    dashboard = {
        "uid": "ams-x",
        "annotations": {
            "list": [
                {"datasource": {"type": "datasource", "uid": "grafana"}},
            ],
        },
    }

    found = sync_module.collect_placeholder_uids(dashboard)

    assert found == set()


def test_build_uid_remap_uses_defaults_when_env_unset() -> None:
    dashboards = [
        {
            "uid": "d",
            "panels": [{"datasource": {"type": "prometheus", "uid": "prometheus"}}],
        }
    ]

    remap = sync_module.build_uid_remap(dashboards, env={})

    assert remap == {"prometheus": "grafanacloud-prom"}


def test_build_uid_remap_env_overrides_default() -> None:
    dashboards = [
        {
            "uid": "d",
            "panels": [{"datasource": {"type": "loki", "uid": "loki"}}],
        }
    ]

    remap = sync_module.build_uid_remap(
        dashboards, env={"GC_LOKI_UID": "grafanacloud-staging-logs"}
    )

    assert remap == {"loki": "grafanacloud-staging-logs"}


def test_build_uid_remap_treats_blank_env_as_unset() -> None:
    """A whitespace-only env var must NOT override the default.

    Without this guard, ``GC_PROMETHEUS_UID=""`` (a frequent
    misconfiguration in CI when a workflow secret/var resolves to empty)
    would set the UID to the empty string and every Prometheus panel
    would silently break.
    """
    dashboards = [
        {
            "uid": "d",
            "panels": [{"datasource": {"type": "prometheus", "uid": "prometheus"}}],
        }
    ]

    remap = sync_module.build_uid_remap(
        dashboards, env={"GC_PROMETHEUS_UID": "   "}
    )

    assert remap == {"prometheus": "grafanacloud-prom"}


def test_build_uid_remap_aborts_when_cloudwatch_unconfigured() -> None:
    """Missing ``GC_CLOUDWATCH_UID`` must abort with a non-zero exit.

    CloudWatch has no default because the AWS-connector UID is
    auto-generated per stack. Letting the sync proceed without it would
    push dashboards whose CloudWatch panels resolve to nothing — exactly
    the failure mode this remap exists to prevent.
    """
    dashboards = [
        {
            "uid": "d",
            "panels": [{"datasource": {"type": "cloudwatch", "uid": "cloudwatch"}}],
        }
    ]

    with pytest.raises(SystemExit) as exc_info:
        sync_module.build_uid_remap(dashboards, env={})

    assert exc_info.value.code == 2


def test_build_uid_remap_non_strict_tolerates_missing_cloudwatch() -> None:
    """``strict=False`` must NOT abort on a missing CW UID.

    The dry-run / validate CI job runs on every PR (and from fork PRs
    without access to repo variables), so it cannot require
    ``GC_CLOUDWATCH_UID``. Strict mode is reserved for the live sync.
    """
    dashboards = [
        {
            "uid": "d",
            "panels": [
                {"datasource": {"type": "prometheus", "uid": "prometheus"}},
                {"datasource": {"type": "cloudwatch", "uid": "cloudwatch"}},
            ],
        }
    ]

    remap = sync_module.build_uid_remap(dashboards, env={}, strict=False)

    # Prometheus default still resolves; CloudWatch is silently omitted.
    assert remap == {"prometheus": "grafanacloud-prom"}


def test_main_dry_run_does_not_require_cloudwatch_uid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: dry-run on a CW-using dashboard must succeed with no env.

    Regression guard against the original strict-by-default dry-run
    that broke the dashboards-validate CI job on PRs.
    """
    path = tmp_path / "d.json"
    path.write_text(
        json.dumps(
            {
                "uid": "ams-d",
                "title": "D",
                "panels": [
                    {"datasource": {"type": "cloudwatch", "uid": "cloudwatch"}},
                ],
            }
        )
    )
    monkeypatch.delenv("GC_CLOUDWATCH_UID", raising=False)

    exit_code = sync_module.main(["--dashboards-dir", str(tmp_path), "--dry-run"])

    assert exit_code == 0


def test_build_uid_remap_skips_unused_placeholders() -> None:
    """An unset ``GC_CLOUDWATCH_UID`` must not block a CW-free batch.

    If a dashboard set references only Prometheus, the remap should
    succeed without ``GC_CLOUDWATCH_UID`` being set — the env var is
    only required when at least one dashboard references the
    ``cloudwatch`` placeholder.
    """
    dashboards = [
        {
            "uid": "d",
            "panels": [{"datasource": {"type": "prometheus", "uid": "prometheus"}}],
        }
    ]

    remap = sync_module.build_uid_remap(dashboards, env={})

    assert remap == {"prometheus": "grafanacloud-prom"}
    assert "cloudwatch" not in remap


def test_remap_datasource_uids_rewrites_nested_references() -> None:
    """``datasource.uid`` rewrites must reach every nesting level.

    Targets inside panels, datasources on templating variables, and
    datasources on annotations all need the same treatment — otherwise
    a single missed nest point silently breaks a panel in GC.
    """
    dashboard = {
        "uid": "ams-x",
        "panels": [
            {
                "datasource": {"type": "prometheus", "uid": "prometheus"},
                "targets": [
                    {"datasource": {"type": "loki", "uid": "loki"}, "expr": "up"},
                ],
            },
        ],
        "templating": {
            "list": [
                {"datasource": {"type": "tempo", "uid": "tempo"}},
            ],
        },
    }

    remap = {
        "prometheus": "grafanacloud-prom",
        "loki": "grafanacloud-logs",
        "tempo": "grafanacloud-traces",
    }
    remapped = sync_module.remap_datasource_uids(dashboard, remap)

    assert remapped["panels"][0]["datasource"]["uid"] == "grafanacloud-prom"
    assert remapped["panels"][0]["targets"][0]["datasource"]["uid"] == "grafanacloud-logs"
    assert remapped["templating"]["list"][0]["datasource"]["uid"] == "grafanacloud-traces"
    # Types must be preserved — GC's hosted Prometheus is still
    # ``type=prometheus``; remapping the UID alone is enough.
    assert remapped["panels"][0]["datasource"]["type"] == "prometheus"
    # Sibling fields on the target must survive the walk.
    assert remapped["panels"][0]["targets"][0]["expr"] == "up"


def test_remap_datasource_uids_does_not_mutate_input() -> None:
    """The original dashboard dict must be left untouched.

    Callers keep the pre-remap dashboard around for diagnostics
    (``--dry-run`` log lines, future ``--diff`` mode). Mutating in
    place would corrupt those.
    """
    dashboard = {
        "uid": "ams-x",
        "panels": [{"datasource": {"type": "prometheus", "uid": "prometheus"}}],
    }

    sync_module.remap_datasource_uids(dashboard, {"prometheus": "grafanacloud-prom"})

    assert dashboard["panels"][0]["datasource"]["uid"] == "prometheus"


def test_remap_datasource_uids_leaves_unmapped_uids_alone() -> None:
    """UIDs not in the remap (e.g. ``grafana`` built-in) must pass through."""
    dashboard = {
        "uid": "ams-x",
        "annotations": {
            "list": [{"datasource": {"type": "datasource", "uid": "grafana"}}],
        },
    }

    remapped = sync_module.remap_datasource_uids(
        dashboard, {"prometheus": "grafanacloud-prom"}
    )

    assert remapped["annotations"]["list"][0]["datasource"]["uid"] == "grafana"


def test_main_live_run_remaps_uids_before_posting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: the payload sent to GC must carry remapped UIDs.

    Without remapping the placeholder UIDs survived to GC and every
    panel resolved to "datasource not found" — the failure mode that
    motivated this whole pass.
    """
    path = tmp_path / "d.json"
    path.write_text(
        json.dumps(
            {
                "uid": "ams-d",
                "title": "D",
                "panels": [
                    {"datasource": {"type": "prometheus", "uid": "prometheus"}},
                    {"datasource": {"type": "cloudwatch", "uid": "cloudwatch"}},
                ],
            }
        )
    )
    mock_post = MagicMock(return_value=200)
    monkeypatch.setattr(sync_module, "post_dashboard", mock_post)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "test-token")
    monkeypatch.setenv("GC_CLOUDWATCH_UID", "stack-specific-cw")

    exit_code = sync_module.main(
        [
            "--dashboards-dir",
            str(tmp_path),
            "--stack-url",
            "https://stack.grafana.net",
        ]
    )

    assert exit_code == 0
    assert mock_post.call_count == 1
    posted_payload = mock_post.call_args.args[2]
    panels = posted_payload["dashboard"]["panels"]
    assert panels[0]["datasource"]["uid"] == "grafanacloud-prom"
    assert panels[1]["datasource"]["uid"] == "stack-specific-cw"

