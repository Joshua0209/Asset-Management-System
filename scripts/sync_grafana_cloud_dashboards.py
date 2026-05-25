"""One-shot upload of repo-side Grafana dashboards to a Grafana Cloud stack.

Phase 4 of `docs/plans/observability-prod-migration-plan.md`. Transient:
this script is deleted in Phase 6 once Grafana Cloud is the source of
truth for dashboards.

Usage:

    GRAFANA_CLOUD_API_KEY=<key> python scripts/sync_grafana_cloud_dashboards.py \\
        --stack-url https://<stack>.grafana.net

    python scripts/sync_grafana_cloud_dashboards.py --dry-run   # parse, no POST

Reads every `*.json` under `config/grafana/dashboards/`, wraps each in the
dashboards-DB payload shape (`{"dashboard": ..., "overwrite": true}`), and
POSTs to `<stack-url>/api/dashboards/db`. Idempotent: existing dashboards
are upserted by `uid`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# Anchor on this file's location rather than CWD so the runbook command
# (`python scripts/sync_grafana_cloud_dashboards.py`) works from the repo
# root AND `python sync_grafana_cloud_dashboards.py` works from inside
# `scripts/`. ``parent.parent`` is the repo root.
DEFAULT_DASHBOARDS_DIR = (
    Path(__file__).resolve().parent.parent / "config" / "grafana" / "dashboards"
)
API_PATH = "/api/dashboards/db"
HTTP_TIMEOUT_SECONDS = 30
# Fail-fast threshold for consecutive transport errors (URLError, not
# HTTPError — the latter implies GC is reachable). After this many
# in a row we assume GC is unreachable and abort the loop rather than
# wait out ``len(dashboards) * HTTP_TIMEOUT_SECONDS`` (6 × 30 s = 3 min
# on a network outage). Operator gets the partial-failure summary
# immediately instead of after a long CI hang.
#
# Raised from 2 to 3 (PR review LOW): with threshold 2, a single bad
# dashboard transient at iteration 1 followed by a coincidental
# transient at iteration 2 aborts the remaining four dashboards even
# though GC is reachable. Threshold 3 keeps the bound on the
# pathological-outage hang at 3 × 30s = 90s (still well under CI job
# step timeouts) while letting an isolated double-blip recover via
# the counter-reset on the next non-599 status.
_CONSECUTIVE_TRANSPORT_FAIL_LIMIT = 3


def load_dashboards(
    dashboards_dir: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Read every ``*.json`` file under ``dashboards_dir``.

    Returns ``(valid_dashboards, malformed_filenames)``. A malformed
    dashboard (invalid JSON, ``OSError`` opening the file, missing
    required ``uid`` field) is recorded as a filename in the second
    list rather than raising — without this, a single bad JSON would
    abort the whole sync loop with a raw stacktrace mid-summary,
    masking any ``OK`` lines from earlier dashboards in iteration
    order. ``main()`` surfaces both lists in the final summary so
    operators see exactly what landed and what didn't.

    The ``--dry-run`` CI gate (``dashboards-validate`` job) still
    catches malformed dashboards before they reach this loop in
    production; this is defense in depth for the case where the
    operator runs the script from a laptop against a JSON that was
    edited but not pushed yet.
    """
    loaded: list[dict[str, Any]] = []
    malformed: list[str] = []
    for path in sorted(dashboards_dir.glob("*.json")):
        try:
            with path.open() as fh:
                dashboard: dict[str, Any] = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            sys.stderr.write(f"FAIL: {path.name} -> malformed ({exc})\n")
            malformed.append(path.name)
            continue
        if "uid" not in dashboard:
            sys.stderr.write(
                f"FAIL: {path.name} -> missing required 'uid' field\n"
            )
            malformed.append(path.name)
            continue
        loaded.append(dashboard)
    return loaded, malformed


def build_payload(dashboard: dict[str, Any]) -> dict[str, Any]:
    """Wrap a dashboard JSON in the Grafana dashboards-DB envelope."""
    return {"dashboard": dashboard, "overwrite": True}


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Disable urllib's automatic redirect-following.

    A 3xx response to ``POST /api/dashboards/db`` is never a legitimate
    Grafana Cloud API result — it usually means the API key is missing
    the dashboards-write scope and GC redirected to a login/SSO page.
    urllib's default handler would follow the redirect (often as GET),
    fetch the final HTML, and surface a 200, masking the auth problem.
    Returning the original 3xx via HTTPError makes the failure visible
    to ``post_dashboard``'s exception arm.
    """

    def http_error_302(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
    ) -> Any:
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def post_dashboard(stack_url: str, api_key: str, payload: dict[str, Any]) -> int:
    """POST one dashboard payload to the Grafana stack. Returns HTTP status.

    Uses an opener that refuses to follow 3xx redirects — see
    ``_NoRedirectHandler``. Catches both ``urllib.error.HTTPError``
    (non-2xx response from GC, including the now-visible 3xx auth-
    redirect case) and ``urllib.error.URLError`` (DNS failure,
    connection refused, TLS error, socket timeout). A URL-level
    failure returns ``599`` so ``main()`` can treat it as a publish
    failure rather than aborting the loop and leaving the GC stack
    with a partially-published dashboard set.

    On failure, writes a clear ``FAIL: <uid> -> <code> <reason>`` line
    to stderr including the status code so the operator can recognise
    the 3xx auth-redirect symptom without needing to grep the source.
    """
    url = stack_url.rstrip("/") + API_PATH
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    uid = payload["dashboard"].get("uid", "<unknown>")
    try:
        with _NO_REDIRECT_OPENER.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            status: int = response.status
            return status
    except urllib.error.HTTPError as exc:
        hint = ""
        if 300 <= exc.code < 400:
            hint = (
                " (3xx on POST usually means the API key is missing the "
                "dashboards-write scope; check GC API key permissions)"
            )
        sys.stderr.write(f"FAIL: {uid} -> {exc.code} {exc.reason}{hint}\n")
        return exc.code
    except urllib.error.URLError as exc:
        # DNS / TCP / TLS-level failures (HTTPError is a subclass of URLError
        # and is caught above first). 599 is the conventional client-side
        # transport-failed sentinel — it triggers main()'s failure path.
        sys.stderr.write(f"FAIL: {uid} -> URL error: {exc.reason}\n")
        return 599


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dashboards-dir",
        type=Path,
        default=DEFAULT_DASHBOARDS_DIR,
        help=f"Directory containing dashboard JSONs (default: {DEFAULT_DASHBOARDS_DIR})",
    )
    parser.add_argument(
        "--stack-url",
        default="",
        help=(
            "Grafana Cloud stack URL, e.g. https://<your-stack-slug>.grafana.net. "
            "Required when not in --dry-run mode."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse dashboards and print what would be POSTed; do not send HTTP requests.",
    )
    args = parser.parse_args(argv)

    if not args.dashboards_dir.is_dir():
        sys.stderr.write(
            f"Dashboards directory not found: {args.dashboards_dir}\n"
        )
        return 2

    dashboards, malformed = load_dashboards(args.dashboards_dir)
    if not dashboards and not malformed:
        sys.stderr.write(f"No dashboards found under {args.dashboards_dir}\n")
        return 1

    if args.dry_run:
        if dashboards:
            print(f"DRY RUN: would POST {len(dashboards)} dashboard(s):")
            for dashboard in dashboards:
                print(
                    f"  - uid={dashboard['uid']}  "
                    f"title={dashboard.get('title', '<no-title>')}"
                )
        if malformed:
            sys.stderr.write(
                f"\n{len(malformed)} dashboard(s) malformed: "
                f"{', '.join(malformed)}\n"
            )
            return 1
        return 0

    api_key = os.environ.get("GRAFANA_CLOUD_API_KEY", "")
    if not api_key:
        sys.stderr.write(
            "GRAFANA_CLOUD_API_KEY is unset; export it or pass --dry-run\n"
        )
        raise SystemExit(2)
    if not args.stack_url:
        sys.stderr.write("--stack-url is required when not in --dry-run mode\n")
        raise SystemExit(2)
    # M3 finding from the third review: refuse to send the bearer token over
    # plaintext OR to an unexpected protocol scheme. Without this guard:
    #   * A mistyped ``--stack-url http://...`` (or an env-var-driven runbook
    #     that lost the ``s``) sends ``Authorization: Bearer <GC_API_KEY>``
    #     in cleartext to anyone on the network path.
    #   * A misconfigured stack URL pointing at the EC2 IMDS endpoint
    #     ``http://169.254.169.254/...`` (or any internal http:// URL)
    #     would gladly send the GC token to the wrong server.
    #   * Non-HTTP schemes (file://, ftp://, ldap://) would surprise the
    #     reader of any error trace without any legitimate use case here.
    # The Grafana Cloud stack URL is always ``https://<slug>.grafana.net``
    # — there is no test/dev mode that legitimately needs http://. Fail
    # closed.
    if not args.stack_url.startswith("https://"):
        sys.stderr.write(
            "--stack-url must use the https:// scheme to avoid leaking the "
            "GRAFANA_CLOUD_API_KEY over plaintext. Got: "
            f"{args.stack_url.split(':', 1)[0] or '(empty)'}://...\n"
        )
        raise SystemExit(2)

    failed_uids: list[str] = []
    consecutive_transport_fails = 0
    skipped_after_abort: list[str] = []
    aborted = False
    for dashboard in dashboards:
        if aborted:
            # Don't even attempt the post — GC has already shown itself
            # unreachable. Record the uid so the summary reports the
            # full unattempted set, not just the loop-end snapshot.
            skipped_after_abort.append(str(dashboard.get("uid", "<unknown>")))
            continue
        status = post_dashboard(args.stack_url, api_key, build_payload(dashboard))
        uid = str(dashboard.get("uid", "<unknown>"))
        # Strictly 2xx is success. A 3xx redirect (e.g. GC returning a
        # 302 to a login page when the token has insufficient scope) is
        # NOT success — the API never legitimately redirects on POST.
        # _NoRedirectHandler turns 3xx into an HTTPError so post_dashboard's
        # FAIL line is emitted with a hint pointing at API-key scope.
        if 200 <= status < 300:
            print(f"OK  uid={uid} status={status}")
            consecutive_transport_fails = 0
        else:
            failed_uids.append(uid)
            # post_dashboard returns 599 specifically for transport-
            # level URLError (DNS, TCP, TLS). HTTPError-class failures
            # (4xx/5xx) come back with the real code — those mean GC
            # *is* reachable, so don't trip the fail-fast.
            if status == 599:
                consecutive_transport_fails += 1
                if consecutive_transport_fails >= _CONSECUTIVE_TRANSPORT_FAIL_LIMIT:
                    sys.stderr.write(
                        f"\nABORT: {consecutive_transport_fails} consecutive transport "
                        f"failures against {args.stack_url}; assuming GC is unreachable "
                        "and skipping the remaining dashboards.\n"
                    )
                    aborted = True
            else:
                consecutive_transport_fails = 0

    # Final summary so an operator scanning CI output doesn't have to
    # grep individual FAIL lines to know how many dashboards failed and
    # which uids need investigation. Malformed files (caught in
    # load_dashboards) are reported alongside publish failures so the
    # operator sees one consolidated count, not two unrelated sections.
    total = len(dashboards) + len(malformed)
    if failed_uids or skipped_after_abort or malformed:
        all_failures = failed_uids + skipped_after_abort + malformed
        parts: list[str] = []
        if skipped_after_abort:
            parts.append(f"{len(skipped_after_abort)} skipped after abort")
        if malformed:
            parts.append(f"{len(malformed)} malformed")
        suffix = f" ({', '.join(parts)})" if parts else ""
        sys.stderr.write(
            f"\n{len(all_failures)} of {total} dashboard(s) failed to publish"
            f"{suffix}: {', '.join(all_failures)}\n"
        )
        return 1
    print(f"\nAll {total} dashboard(s) published successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
