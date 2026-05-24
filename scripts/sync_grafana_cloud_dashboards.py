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


def load_dashboards(dashboards_dir: Path) -> list[dict[str, Any]]:
    """Read every `*.json` file under `dashboards_dir`. Raises if any
    dashboard lacks a `uid` (the API needs it for idempotent upsert)."""
    loaded: list[dict[str, Any]] = []
    for path in sorted(dashboards_dir.glob("*.json")):
        with path.open() as fh:
            dashboard: dict[str, Any] = json.load(fh)
        if "uid" not in dashboard:
            raise ValueError(f"Dashboard {path} is missing required 'uid' field")
        loaded.append(dashboard)
    return loaded


def build_payload(dashboard: dict[str, Any]) -> dict[str, Any]:
    """Wrap a dashboard JSON in the Grafana dashboards-DB envelope."""
    return {"dashboard": dashboard, "overwrite": True}


def post_dashboard(stack_url: str, api_key: str, payload: dict[str, Any]) -> int:
    """POST one dashboard payload to the Grafana stack. Returns HTTP status.

    Catches both ``urllib.error.HTTPError`` (non-2xx response from GC) and
    ``urllib.error.URLError`` (DNS failure, connection refused, TLS error,
    socket timeout). A URL-level failure returns ``599`` so ``main()`` can
    treat it as a publish failure rather than aborting the loop and
    leaving the GC stack with a partially-published dashboard set.
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
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            status: int = response.status
            return status
    except urllib.error.HTTPError as exc:
        sys.stderr.write(f"FAIL: {uid} -> {exc.code} {exc.reason}\n")
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
        help="Grafana Cloud stack URL, e.g. https://ams.grafana.net",
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

    dashboards = load_dashboards(args.dashboards_dir)
    if not dashboards:
        sys.stderr.write(f"No dashboards found under {args.dashboards_dir}\n")
        return 1

    if args.dry_run:
        print(f"DRY RUN: would POST {len(dashboards)} dashboard(s):")
        for dashboard in dashboards:
            print(f"  - uid={dashboard['uid']}  title={dashboard.get('title', '<no-title>')}")
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

    failures = 0
    for dashboard in dashboards:
        status = post_dashboard(args.stack_url, api_key, build_payload(dashboard))
        # Strictly 2xx is success. A 3xx redirect (e.g. GC returning a
        # 302 to a login page when the token has insufficient scope) is
        # NOT success — the API never legitimately redirects on POST.
        if 200 <= status < 300:
            print(f"OK  uid={dashboard['uid']} status={status}")
        else:
            failures += 1
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
