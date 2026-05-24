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

DEFAULT_DASHBOARDS_DIR = Path("config/grafana/dashboards")
API_PATH = "/api/dashboards/db"


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
    """POST one dashboard payload to the Grafana stack. Returns HTTP status."""
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
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status: int = response.status
            return status
    except urllib.error.HTTPError as exc:
        sys.stderr.write(
            f"FAIL: {payload['dashboard'].get('uid', '<unknown>')} -> {exc.code} {exc.reason}\n"
        )
        return exc.code


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
        if status >= 400:
            failures += 1
        else:
            print(f"OK  uid={dashboard['uid']} status={status}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
