"""One-shot upload of repo-side Grafana dashboards to a Grafana Cloud stack.

Phase 4 of `docs/plans/observability-prod-migration-plan.md`. Transient:
this script is deleted in Phase 6 once Grafana Cloud is the source of
truth for dashboards.

Usage:

    GRAFANA_CLOUD_API_KEY=<key> \\
    GC_CLOUDWATCH_UID=<stack-specific-uid> \\
        python scripts/sync_grafana_cloud_dashboards.py \\
        --stack-url https://<stack>.grafana.net

    python scripts/sync_grafana_cloud_dashboards.py --dry-run   # parse, no POST

Reads every `*.json` under `config/grafana/dashboards/`, wraps each in the
dashboards-DB payload shape (`{"dashboard": ..., "overwrite": true}`), and
POSTs to `<stack-url>/api/dashboards/db`. Idempotent: existing dashboards
are upserted by `uid`.

Datasource UID remapping
------------------------

Dashboard JSONs reference datasources by the placeholder UIDs the local
docker-compose stack used to provision (``prometheus``, ``loki``,
``cloudwatch``, ``tempo``, ``pyroscope``). Grafana Cloud assigns its own
UIDs to the hosted datasources (``grafanacloud-prom``, ``grafanacloud-logs``,
``grafanacloud-traces``, ``grafanacloud-profiles``) and the AWS CloudWatch
connector gets an auto-generated, stack-specific UID. Before POSTing, the
script rewrites every ``datasource.uid`` in the dashboard payload from the
placeholder to the real GC UID, so panels resolve their datasource in the
stack the dashboards land in. Defaults match the GC standard names; the
stack-specific CloudWatch UID is taken from ``GC_CLOUDWATCH_UID`` and is
required only if any dashboard references the ``cloudwatch`` placeholder.
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

# Placeholder UIDs the dashboard JSONs use (left over from the docker-
# compose era when Grafana was provisioned with datasources.yml pinning
# these names). Each maps to either a GC-standard hosted-datasource UID
# or, for CloudWatch, an env-var lookup since the AWS connector picks an
# auto-generated UID per stack.
#
# ``grafana`` is Grafana's built-in datasource (annotations, etc.) and has
# UID literally ``grafana`` in every instance — leave it alone, never
# substitute.
_PLACEHOLDER_UIDS: frozenset[str] = frozenset(
    {"prometheus", "loki", "tempo", "pyroscope", "cloudwatch"}
)
_DEFAULT_UID_REMAP: dict[str, str] = {
    "prometheus": "grafanacloud-prom",
    "loki": "grafanacloud-logs",
    "tempo": "grafanacloud-traces",
    "pyroscope": "grafanacloud-profiles",
    # No default for ``cloudwatch`` — the AWS connector's UID is
    # auto-generated per stack (e.g. ``cfmzw3p1ziebkb``) and must be
    # supplied via ``GC_CLOUDWATCH_UID``. ``build_uid_remap`` validates
    # this if any dashboard references the placeholder.
}
# Env-var names that override each default. One per placeholder so a
# future GC stack reshuffle does not need a code change — just an env
# var update in CI.
_UID_REMAP_ENV: dict[str, str] = {
    "prometheus": "GC_PROMETHEUS_UID",
    "loki": "GC_LOKI_UID",
    "tempo": "GC_TEMPO_UID",
    "pyroscope": "GC_PYROSCOPE_UID",
    "cloudwatch": "GC_CLOUDWATCH_UID",
}


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


def collect_placeholder_uids(dashboard: dict[str, Any]) -> set[str]:
    """Return the subset of ``_PLACEHOLDER_UIDS`` that ``dashboard`` references.

    Walks every ``datasource.uid`` in the tree (panels, targets, templating
    variables, annotations) so ``build_uid_remap`` knows exactly which env
    vars are load-bearing for this batch. Without this, missing
    ``GC_CLOUDWATCH_UID`` would only fail at GC-side at panel-render time
    (silently empty panels), not at sync time.
    """
    found: set[str] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            ds = obj.get("datasource")
            if isinstance(ds, dict):
                uid = ds.get("uid")
                if isinstance(uid, str) and uid in _PLACEHOLDER_UIDS:
                    found.add(uid)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(dashboard)
    return found


def build_uid_remap(
    dashboards: Sequence[dict[str, Any]],
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Resolve the placeholder-UID → real-UID mapping for this batch.

    Reads ``_UID_REMAP_ENV`` from ``env`` (defaults to ``os.environ``),
    falls back to ``_DEFAULT_UID_REMAP`` for entries with no override,
    and raises ``SystemExit(2)`` with a clear message if any placeholder
    used by the dashboards has no real UID configured. The error names
    the missing env var so an operator running this from a laptop or
    reading a CI failure can fix it without grepping the source.
    """
    env_map: dict[str, str] = dict(env) if env is not None else dict(os.environ)
    used: set[str] = set()
    for dashboard in dashboards:
        used |= collect_placeholder_uids(dashboard)
    remap: dict[str, str] = {}
    missing: list[str] = []
    for placeholder in used:
        env_name = _UID_REMAP_ENV[placeholder]
        env_value = env_map.get(env_name, "").strip()
        if env_value:
            remap[placeholder] = env_value
            continue
        default = _DEFAULT_UID_REMAP.get(placeholder)
        if default is not None:
            remap[placeholder] = default
            continue
        missing.append(f"{placeholder} (set {env_name})")
    if missing:
        sys.stderr.write(
            "Cannot resolve datasource UID for the following placeholder(s) "
            "referenced by dashboards: "
            f"{', '.join(sorted(missing))}. Set the named env var(s) and re-run.\n"
        )
        raise SystemExit(2)
    return remap


def remap_datasource_uids(
    dashboard: dict[str, Any],
    remap: dict[str, str],
) -> dict[str, Any]:
    """Return a deep copy of ``dashboard`` with placeholder UIDs rewritten.

    Walks the entire dashboard tree (panels, nested rows, targets,
    templating variables, annotations) and rewrites ``datasource.uid``
    whenever the current value appears in ``remap``. Returns a new dict
    so the caller can keep the original around for diagnostics; the
    input is not mutated.

    The ``datasource.type`` field is left alone — GC's hosted Prometheus
    is still type ``prometheus``, GC's Loki is still type ``loki``, etc.
    Only the UID changes.
    """
    if not remap:
        # No placeholders referenced — defensive deep copy still preserves
        # the immutability contract callers can rely on.
        cloned: dict[str, Any] = json.loads(json.dumps(dashboard))
        return cloned

    def walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            new: dict[str, Any] = {}
            for key, value in obj.items():
                if key == "datasource" and isinstance(value, dict):
                    new[key] = _maybe_remap_datasource(value, remap)
                else:
                    new[key] = walk(value)
            return new
        if isinstance(obj, list):
            return [walk(item) for item in obj]
        return obj

    walked = walk(dashboard)
    assert isinstance(walked, dict)
    return walked


def _maybe_remap_datasource(
    datasource: dict[str, Any],
    remap: dict[str, str],
) -> dict[str, Any]:
    uid = datasource.get("uid")
    if isinstance(uid, str) and uid in remap:
        return {**datasource, "uid": remap[uid]}
    return dict(datasource)


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
        # Resolve the UID remap even in dry-run so CI catches a missing
        # GC_CLOUDWATCH_UID before the live sync ever runs. If env vars
        # are absent on a developer laptop the standard defaults still
        # let the dry run finish; only ``cloudwatch`` (which has no
        # default) can block.
        remap = build_uid_remap(dashboards)
        if dashboards:
            print(f"DRY RUN: would POST {len(dashboards)} dashboard(s):")
            for dashboard in dashboards:
                print(
                    f"  - uid={dashboard['uid']}  "
                    f"title={dashboard.get('title', '<no-title>')}"
                )
            if remap:
                print("\nDatasource UID remap:")
                for placeholder, real in sorted(remap.items()):
                    print(f"  {placeholder} -> {real}")
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

    # Build the UID remap BEFORE the publish loop so a missing
    # GC_CLOUDWATCH_UID aborts with a clear error instead of silently
    # posting dashboards whose CloudWatch panels would render empty.
    remap = build_uid_remap(dashboards)
    if remap:
        print("Datasource UID remap:")
        for placeholder, real in sorted(remap.items()):
            print(f"  {placeholder} -> {real}")
        print()

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
        remapped = remap_datasource_uids(dashboard, remap)
        status = post_dashboard(args.stack_url, api_key, build_payload(remapped))
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
