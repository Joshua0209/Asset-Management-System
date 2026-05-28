"""Sync repo-side Grafana dashboards and alert rules to a Grafana Cloud stack.

Phase 4 of `docs/plans/observability-prod-migration-plan.md`. Transient:
this script is deleted in Phase 6 once Grafana Cloud is the source of
truth for dashboards.

Usage:

    GRAFANA_CLOUD_API_KEY=<key> \\
    GC_CLOUDWATCH_UID=<stack-specific-uid> \\
        python scripts/sync_grafana_cloud_dashboards.py \\
        --stack-url https://<stack>.grafana.net

    python scripts/sync_grafana_cloud_dashboards.py --dry-run   # parse, no POST

Two surfaces, selected by ``--targets``:

* ``dashboards`` (the default — keeps pre-alerts operator and test callers
  working unchanged): reads every ``*.json`` under
  ``config/grafana/dashboards/``, wraps each in the dashboards-DB envelope
  (``{"dashboard": ..., "overwrite": true}``) and POSTs to
  ``<stack-url>/api/dashboards/db``.
* ``alerts``: reads ``config/grafana/alerts/`` (``contact-points.json``,
  ``notification-policy.json``, ``rules/*.json``) and upserts the email
  contact point, the root notification policy, and every alert rule via the
  Grafana Alerting provisioning API (``/api/v1/provisioning/*``). Recipients
  are NOT committed — they come from ``--recipients`` (CSV) or the
  ``GC_ALERT_EMAIL_RECIPIENTS`` env var / GitHub secret and are substituted
  into the contact-point template at deploy time.
* ``all``: dashboards then alerts (what CI runs; runbook in
  ``infra/grafana-cloud/README.md`` §"Alert provisioning").

Both surfaces are idempotent: dashboards and rules upsert by ``uid``, the
singleton root policy is replaced. ``--dry-run`` parses and prints what
would be sent without POSTing and tolerates missing secrets/UIDs so the
PR-side validate gate passes on fork PRs.

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

Alert rules carry the same placeholder UIDs but in the flat
``data[].datasourceUid`` field (the provisioning API's shape) rather than a
nested ``datasource.uid``; both forms are walked and remapped the same way.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Any, NamedTuple

# Anchor on this file's location rather than CWD so the runbook command
# (`python scripts/sync_grafana_cloud_dashboards.py`) works from the repo
# root AND `python sync_grafana_cloud_dashboards.py` works from inside
# `scripts/`. ``parent.parent`` is the repo root.
DEFAULT_DASHBOARDS_DIR = (
    Path(__file__).resolve().parent.parent / "config" / "grafana" / "dashboards"
)
DEFAULT_ALERTS_DIR = (
    Path(__file__).resolve().parent.parent / "config" / "grafana" / "alerts"
)
API_PATH = "/api/dashboards/db"
# Grafana Alerting provisioning API. Used by the alerts pass to upsert
# contact points, the root notification policy, and individual rules.
# See https://grafana.com/docs/grafana/latest/developers/http_api/alerting_provisioning/
PROVISIONING_CONTACT_POINTS_PATH = "/api/v1/provisioning/contact-points"
PROVISIONING_POLICIES_PATH = "/api/v1/provisioning/policies"
PROVISIONING_ALERT_RULES_PATH = "/api/v1/provisioning/alert-rules"
HTTP_TIMEOUT_SECONDS = 30
# Fail-fast threshold for consecutive transport errors (URLError, not
# HTTPError — the latter implies GC is reachable). After this many
# in a row we assume GC is unreachable and abort the loop rather than
# wait out ``len(dashboards) * HTTP_TIMEOUT_SECONDS`` (6 × 30 s = 3 min
# on a network outage). Operator gets the partial-failure summary
# immediately instead of after a long CI hang.
#
# 3 balances two failure modes: a lower limit lets a couple of isolated
# transient blips (with GC actually reachable) abort the rest of the
# batch, while a higher limit lengthens the worst-case hang on a true
# outage. At 3 the outage bound is 3 × 30s = 90s (under CI step
# timeouts), and an isolated double-blip still recovers via the
# counter-reset on the next non-599 status.
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


class AlertResources(NamedTuple):
    """Bundle of Grafana Cloud alerting resources loaded from disk.

    ``contact_point`` and ``notification_policy`` are required; either being
    ``None`` means the corresponding required file was missing or malformed
    (the offending filename is in the companion ``malformed`` list returned
    by ``load_alert_resources``). ``rules`` is the flat aggregate of every
    rule across every ``rules/*.json`` file, in filename-sorted order so a
    repeat sync POSTs rules in the same sequence as the previous run.
    """

    contact_point: dict[str, Any] | None
    notification_policy: dict[str, Any] | None
    rules: tuple[dict[str, Any], ...]

    @property
    def is_empty(self) -> bool:
        """Nothing loaded at all. Distinct from a load that produced
        ``malformed`` entries — that is a failure, this is an empty dir."""
        return (
            self.contact_point is None
            and self.notification_policy is None
            and not self.rules
        )

    @property
    def required_present(self) -> bool:
        """Both required singletons (contact point + root policy) loaded
        successfully. ``False`` means at least one is in ``malformed``."""
        return (
            self.contact_point is not None
            and self.notification_policy is not None
        )


def load_alert_resources(
    alerts_dir: Path,
) -> tuple[AlertResources, list[str]]:
    """Load alert config files under ``alerts_dir``.

    Expected layout::

        alerts_dir/
          contact-points.json       # required, single contact point object
          notification-policy.json  # required, root policy object
          rules/
            *.json                  # each: {"rules": [<rule>, <rule>, ...]}

    Returns ``(AlertResources, malformed_filenames)``. Same graceful-
    degradation contract as ``load_dashboards``: missing required files
    or invalid JSON are recorded by filename in the second list rather
    than raising, so ``main()`` surfaces them in the final summary
    alongside publish failures instead of aborting with a bare
    stacktrace. Each individual rule must carry a ``uid`` (used as the
    idempotency key for upsert); files containing a rule without ``uid``
    are reported as malformed and ALL rules from that file are dropped
    so the operator's editor can catch the typo before GC sees it.
    """
    malformed: list[str] = []
    contact_point: dict[str, Any] | None = _load_required_json(
        alerts_dir / "contact-points.json", malformed
    )
    notification_policy: dict[str, Any] | None = _load_required_json(
        alerts_dir / "notification-policy.json", malformed
    )

    rules: list[dict[str, Any]] = []
    rules_dir = alerts_dir / "rules"
    if rules_dir.is_dir():
        for path in sorted(rules_dir.glob("*.json")):
            try:
                with path.open() as fh:
                    payload: Any = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                sys.stderr.write(f"FAIL: {path.name} -> malformed ({exc})\n")
                malformed.append(path.name)
                continue
            file_rules = (
                payload.get("rules") if isinstance(payload, dict) else None
            )
            if not isinstance(file_rules, list):
                sys.stderr.write(
                    f"FAIL: {path.name} -> missing required 'rules' array\n"
                )
                malformed.append(path.name)
                continue
            if any(not isinstance(r, dict) or "uid" not in r for r in file_rules):
                sys.stderr.write(
                    f"FAIL: {path.name} -> at least one rule missing 'uid'\n"
                )
                malformed.append(path.name)
                continue
            rules.extend(file_rules)

    return (
        AlertResources(
            contact_point=contact_point,
            notification_policy=notification_policy,
            rules=tuple(rules),
        ),
        malformed,
    )


def find_receiver_binding_errors(resources: AlertResources) -> list[str]:
    """Return one error string per policy/rule that routes to a receiver
    the loaded contact point does not define.

    Grafana routes by receiver *name*: the root policy's ``receiver`` and
    each rule's ``notification_settings.receiver`` must equal the contact
    point's ``name``. A rule naming a nonexistent receiver still upserts
    with HTTP 2xx but silently never delivers — the same "provisions fine,
    never fires" class the rest of this script guards against, except here
    it is "fires but emails nobody". A future edit that renames the contact
    point without updating the rules would pass every HTTP check yet page
    no one, so cross-check the names before publishing.

    A rule with no ``notification_settings.receiver`` is fine: it inherits
    routing from the policy tree. Returns ``[]`` when ``contact_point`` is
    ``None`` (that missing-file case is already reported as malformed).
    """
    if resources.contact_point is None:
        return []
    known = {
        name
        for name in (resources.contact_point.get("name"),)
        if name is not None
    }
    errors: list[str] = []
    policy = resources.notification_policy
    if policy is not None and policy.get("receiver") not in known:
        errors.append(
            f"notification policy routes to receiver "
            f"{policy.get('receiver')!r} but no contact point defines it "
            f"(known: {sorted(known)})"
        )
    for rule in resources.rules:
        receiver = rule.get("notification_settings", {}).get("receiver")
        if receiver is not None and receiver not in known:
            errors.append(
                f"rule {rule.get('uid', '<unknown>')!r} routes to receiver "
                f"{receiver!r} but no contact point defines it "
                f"(known: {sorted(known)})"
            )
    return errors


# Env var feeding ``resolve_recipients`` in live mode. Comma-separated.
# Stored as a GitHub secret so it stays off public PR diffs (recipients
# leak the alerting team's address list otherwise).
_RECIPIENTS_ENV: str = "GC_ALERT_EMAIL_RECIPIENTS"
# Minimal email shape: at least one ``@`` and a ``.`` somewhere AFTER
# the ``@`` (catches the common "pasted a name" mistake without
# importing the email-validator package — keeps the script stdlib only
# per the existing convention). Real validation happens at Grafana's
# side when the contact point is exercised.
_MIN_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def resolve_recipients(
    cli: str | None,
    env: dict[str, str],
    *,
    dry_run: bool,
) -> list[str]:
    """Resolve the alert email recipient list.

    Order: ``cli`` (per-run override) > ``env[_RECIPIENTS_ENV]`` (CI
    secret) > ``SystemExit(2)`` when not in ``dry_run``. ``dry_run``
    returns ``[]`` on absence so PR-side CI without access to the secret
    still passes — the dry-run gate is structural, not behavioural.

    Splits on commas, trims whitespace, drops empty entries, and checks
    each against ``_MIN_EMAIL_SHAPE``. Whitespace-only env values are
    treated as unset (same defence as ``build_uid_remap`` for empty UID
    env vars).
    """
    source = cli if cli is not None else env.get(_RECIPIENTS_ENV, "")
    if source is None or not source.strip():
        if dry_run:
            return []
        sys.stderr.write(
            "Alert recipients are unset. Pass --recipients <a@b.co,c@d.co> "
            f"or export {_RECIPIENTS_ENV} (comma-separated) and re-run.\n"
        )
        raise SystemExit(2)
    recipients = [part.strip() for part in source.split(",")]
    recipients = [r for r in recipients if r]
    for recipient in recipients:
        if not _MIN_EMAIL_SHAPE.match(recipient):
            sys.stderr.write(
                f"Invalid alert recipient: {recipient!r}. Expected an "
                "email of shape user@domain.tld.\n"
            )
            raise SystemExit(2)
    return recipients


def apply_recipients_to_contact_point(
    template: dict[str, Any], recipients: list[str]
) -> dict[str, Any]:
    """Return a deep copy of ``template`` with ``settings.addresses``
    set to the semicolon-joined recipient list.

    Grafana's email contact point stores addresses as a single
    semicolon-delimited string (NOT a JSON array — that quirk pre-dates
    the unified alerting provisioning API). The template's
    ``settings.addresses`` placeholder is replaced; sibling settings
    (``subject``, ``singleEmail``, etc.) survive untouched. The input
    is not mutated so the caller can keep it for diagnostics.
    """
    cloned: dict[str, Any] = json.loads(json.dumps(template))
    settings = cloned.setdefault("settings", {})
    settings["addresses"] = ";".join(recipients)
    return cloned


def _load_required_json(
    path: Path, malformed: list[str]
) -> dict[str, Any] | None:
    """Read a single required JSON file, appending its name to ``malformed``
    on absence/parse-failure rather than raising.

    Internal helper for ``load_alert_resources``: keeps the missing-file
    and malformed-JSON branches symmetric (both end up in the same
    summary line) and avoids three near-identical try/except blocks in
    the caller.
    """
    if not path.is_file():
        sys.stderr.write(f"FAIL: {path.name} -> required file missing\n")
        malformed.append(path.name)
        return None
    try:
        with path.open() as fh:
            data: Any = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        sys.stderr.write(f"FAIL: {path.name} -> malformed ({exc})\n")
        malformed.append(path.name)
        return None
    if not isinstance(data, dict):
        sys.stderr.write(
            f"FAIL: {path.name} -> top-level JSON must be an object\n"
        )
        malformed.append(path.name)
        return None
    return data


def build_payload(dashboard: dict[str, Any]) -> dict[str, Any]:
    """Wrap a dashboard JSON in the Grafana dashboards-DB envelope."""
    return {"dashboard": dashboard, "overwrite": True}


def collect_placeholder_uids(resource: dict[str, Any]) -> set[str]:
    """Return the subset of ``_PLACEHOLDER_UIDS`` that ``resource`` references.

    Walks the resource tree for both Grafana's datasource shapes:

    * Nested form (dashboards): ``{"datasource": {"type": ..., "uid": ...}}``.
    * Flat form (alert rules): a sibling ``"datasourceUid": "..."`` on a
      ``data[]`` query entry. This shape predates the dashboard
      convention and is what the alerting provisioning API expects.

    Knowing the set up front lets ``build_uid_remap`` validate that
    every load-bearing env var (notably ``GC_CLOUDWATCH_UID``) is set
    BEFORE the publish loop — otherwise missing config only surfaces as
    silently empty panels or non-firing rules at render/evaluation time.
    """
    found: set[str] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            ds = obj.get("datasource")
            if isinstance(ds, dict):
                uid = ds.get("uid")
                if isinstance(uid, str) and uid in _PLACEHOLDER_UIDS:
                    found.add(uid)
            flat_uid = obj.get("datasourceUid")
            if isinstance(flat_uid, str) and flat_uid in _PLACEHOLDER_UIDS:
                found.add(flat_uid)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(resource)
    return found


def build_uid_remap(
    dashboards: Sequence[dict[str, Any]],
    env: dict[str, str] | None = None,
    *,
    strict: bool = True,
) -> dict[str, str]:
    """Resolve the placeholder-UID → real-UID mapping for this batch.

    Reads ``_UID_REMAP_ENV`` from ``env`` (defaults to ``os.environ``),
    falls back to ``_DEFAULT_UID_REMAP`` for entries with no override.

    ``strict=True`` (the default, used by the live sync) raises
    ``SystemExit(2)`` with a clear message if any placeholder used by
    the dashboards has no real UID configured. The error names the
    missing env var so an operator can fix it without grepping the
    source. ``strict=False`` (used by the dry-run / validate path)
    silently omits entries that cannot be resolved so the JSON
    structure check stays portable across developer laptops and
    fork-PR builds where ``GC_CLOUDWATCH_UID`` is unavailable.
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
    if missing and strict:
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
                elif (
                    key == "datasourceUid"
                    and isinstance(value, str)
                    and value in remap
                ):
                    # Flat alert-rule shape: ``data[i].datasourceUid`` is a
                    # bare string sibling, not a nested ``datasource`` object.
                    new[key] = remap[value]
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


def _send_provisioning(
    stack_url: str,
    api_key: str,
    method: str,
    path: str,
    payload: dict[str, Any],
    resource_id: str,
) -> int:
    """Issue a single HTTPS request to the Grafana provisioning API.

    Returns the HTTP status code; ``599`` on transport failure; the raw
    4xx/5xx code on HTTP error. Same opener, headers, and error handling
    as ``post_dashboard`` — uses ``_NO_REDIRECT_OPENER`` so a 3xx
    auth-redirect surfaces as a hard failure instead of a misleading
    200 from the SSO landing page. ``resource_id`` is the operator-facing
    identifier (rule/contact-point uid; ``"policy"`` for the root
    notification policy) so the FAIL line tells the operator which
    resource failed without grepping.
    """
    url = stack_url.rstrip("/") + path
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with _NO_REDIRECT_OPENER.open(
            request, timeout=HTTP_TIMEOUT_SECONDS
        ) as response:
            status: int = response.status
            return status
    except urllib.error.HTTPError as exc:
        hint = ""
        if 300 <= exc.code < 400:
            hint = (
                " (3xx on provisioning POST usually means the API key is "
                "missing the alerting-write scope; check GC API key permissions)"
            )
        sys.stderr.write(f"FAIL: {resource_id} -> {exc.code} {exc.reason}{hint}\n")
        return exc.code
    except urllib.error.URLError as exc:
        sys.stderr.write(f"FAIL: {resource_id} -> URL error: {exc.reason}\n")
        return 599


def post_contact_point(
    stack_url: str, api_key: str, contact_point: dict[str, Any]
) -> int:
    """Upsert a contact point via the provisioning API.

    Tries ``POST /api/v1/provisioning/contact-points`` first. The body
    carries the desired ``uid``; on first run GC accepts it (200/201/202).
    On steady-state runs GC returns 409 (contact point exists with that
    uid) and we fall back to ``PUT /api/v1/provisioning/contact-points/{uid}``
    for the actual update. Returns the final HTTP status.
    """
    uid = str(contact_point.get("uid", "<unknown>"))
    status = _send_provisioning(
        stack_url,
        api_key,
        "POST",
        PROVISIONING_CONTACT_POINTS_PATH,
        contact_point,
        uid,
    )
    if status == 409:
        status = _send_provisioning(
            stack_url,
            api_key,
            "PUT",
            f"{PROVISIONING_CONTACT_POINTS_PATH}/{uid}",
            contact_point,
            uid,
        )
    return status


def post_notification_policy(
    stack_url: str, api_key: str, policy: dict[str, Any]
) -> int:
    """Replace the root notification policy.

    The root policy is a singleton — there's no create-vs-update
    distinction, so always PUT. Returns the HTTP status.
    """
    return _send_provisioning(
        stack_url,
        api_key,
        "PUT",
        PROVISIONING_POLICIES_PATH,
        policy,
        "policy",
    )


def post_alert_rule(
    stack_url: str, api_key: str, rule: dict[str, Any]
) -> int:
    """Upsert an alert rule via the provisioning API.

    Same POST → 409 → PUT pattern as ``post_contact_point``.
    """
    uid = str(rule.get("uid", "<unknown>"))
    status = _send_provisioning(
        stack_url,
        api_key,
        "POST",
        PROVISIONING_ALERT_RULES_PATH,
        rule,
        uid,
    )
    if status == 409:
        status = _send_provisioning(
            stack_url,
            api_key,
            "PUT",
            f"{PROVISIONING_ALERT_RULES_PATH}/{uid}",
            rule,
            uid,
        )
    return status


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dashboards-dir",
        type=Path,
        default=DEFAULT_DASHBOARDS_DIR,
        help=f"Directory containing dashboard JSONs (default: {DEFAULT_DASHBOARDS_DIR})",
    )
    parser.add_argument(
        "--alerts-dir",
        type=Path,
        default=DEFAULT_ALERTS_DIR,
        help=(
            "Directory containing alert config (contact-points.json, "
            f"notification-policy.json, rules/*.json). Default: {DEFAULT_ALERTS_DIR}"
        ),
    )
    parser.add_argument(
        "--targets",
        choices=("dashboards", "alerts", "all"),
        default="dashboards",
        help=(
            "Which surfaces to sync. 'dashboards' (default) preserves "
            "the pre-extension behavior — existing operator runs and "
            "tests keep working unchanged. 'all' runs dashboards then "
            "alerts; this is what CI uses. 'alerts' lets an operator "
            "re-sync only the alerts without re-uploading dashboards."
        ),
    )
    parser.add_argument(
        "--recipients",
        default=None,
        help=(
            "Comma-separated email recipients for the alert contact point. "
            f"Overrides ${_RECIPIENTS_ENV}. Required in live alerts mode "
            "(skipped under --dry-run)."
        ),
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
        help="Parse resources and print what would be POSTed; do not send HTTP requests.",
    )
    args = parser.parse_args(argv)

    run_dashboards = args.targets in ("dashboards", "all")
    run_alerts = args.targets in ("alerts", "all")

    # Pre-flight validation. Dashboards-dir presence is hard-required when
    # explicit (``--targets dashboards``) but soft-skipped under the
    # default ``--targets all`` so an operator running the alerts pass
    # against an alerts-only checkout (or in a test fixture that only
    # writes an alerts dir) doesn't have to fabricate a dashboards dir.
    if run_dashboards and not args.dashboards_dir.is_dir():
        if args.targets == "dashboards":
            sys.stderr.write(
                f"Dashboards directory not found: {args.dashboards_dir}\n"
            )
            return 2
        sys.stderr.write(
            f"WARNING: --targets all but {args.dashboards_dir} not found; "
            "skipping the dashboards pass.\n"
        )
        run_dashboards = False
    # Same skip-vs-error split for the alerts dir. Existing dashboard-
    # only tests don't pass --alerts-dir and default to the repo
    # config/grafana/alerts/ path; if that's missing under --targets
    # all (e.g. on a developer machine that hasn't pulled the alerts
    # config yet), silently skip the alerts pass instead of failing.
    if run_alerts and not args.alerts_dir.is_dir():
        if args.targets == "alerts":
            sys.stderr.write(
                f"Alerts directory not found: {args.alerts_dir}\n"
            )
            return 2
        sys.stderr.write(
            f"WARNING: --targets all but {args.alerts_dir} not found; "
            "skipping the alerts pass.\n"
        )
        run_alerts = False

    if not run_dashboards and not run_alerts:
        sys.stderr.write(
            "Nothing to sync: neither dashboards nor alerts pass will run "
            f"(targets={args.targets!r}, dashboards-dir={args.dashboards_dir}, "
            f"alerts-dir={args.alerts_dir}).\n"
        )
        return 1

    # Live-mode-only validation. Skipped under --dry-run so PR-side CI
    # (without secrets) still passes the validate gate.
    api_key = ""
    if not args.dry_run:
        api_key = os.environ.get("GRAFANA_CLOUD_API_KEY", "")
        if not api_key:
            sys.stderr.write(
                "GRAFANA_CLOUD_API_KEY is unset; export it or pass --dry-run\n"
            )
            raise SystemExit(2)
        if not args.stack_url:
            sys.stderr.write("--stack-url is required when not in --dry-run mode\n")
            raise SystemExit(2)
        # Refuse to send the bearer token
        # over plaintext OR to an unexpected protocol scheme. Without this
        # guard, a mistyped --stack-url http://... (or an env-driven runbook
        # that lost the 's') sends Authorization: Bearer <GC_API_KEY> in
        # cleartext. The GC stack URL is always https://<slug>.grafana.net
        # — there is no test/dev mode that legitimately needs http://. Fail
        # closed.
        if not args.stack_url.startswith("https://"):
            sys.stderr.write(
                "--stack-url must use the https:// scheme to avoid leaking the "
                "GRAFANA_CLOUD_API_KEY over plaintext. Got: "
                f"{args.stack_url.split(':', 1)[0] or '(empty)'}://...\n"
            )
            raise SystemExit(2)

    dashboards_exit_ok = True
    alerts_exit_ok = True

    if run_dashboards:
        dashboards_exit_ok = _run_dashboards_pass(args, api_key)

    if run_alerts:
        alerts_exit_ok = _run_alerts_pass(args, api_key)

    return 0 if (dashboards_exit_ok and alerts_exit_ok) else 1


def _run_dashboards_pass(args: argparse.Namespace, api_key: str) -> bool:
    """Execute the dashboards sync pass. Returns True on success.

    Same behavior as the pre-``--targets`` ``main()``: load dashboards,
    optionally dry-run (print + structural-check), else build the UID
    remap and POST each dashboard with transport-fail-aware abort.
    Splits a previously-inline block out of ``main()`` so the alerts
    pass can run alongside it without each branch turning into a
    sprawling if-tree.
    """
    dashboards, malformed = load_dashboards(args.dashboards_dir)
    if not dashboards and not malformed:
        sys.stderr.write(f"No dashboards found under {args.dashboards_dir}\n")
        return False

    if args.dry_run:
        # The dry-run / validate job runs on every PR (including forks)
        # and on developer laptops where stack-specific env vars like
        # GC_CLOUDWATCH_UID are not available. Resolve what we can but
        # do not fail on missing UIDs — strict resolution is the live
        # sync's job.
        remap = build_uid_remap(dashboards, strict=False)
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
            return False
        return True

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
            skipped_after_abort.append(str(dashboard.get("uid", "<unknown>")))
            continue
        remapped = remap_datasource_uids(dashboard, remap)
        status = post_dashboard(args.stack_url, api_key, build_payload(remapped))
        uid = str(dashboard.get("uid", "<unknown>"))
        if 200 <= status < 300:
            print(f"OK  uid={uid} status={status}")
            consecutive_transport_fails = 0
        else:
            failed_uids.append(uid)
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
        return False
    print(f"\nAll {total} dashboard(s) published successfully.")
    return True


def _run_alerts_pass(args: argparse.Namespace, api_key: str) -> bool:
    """Execute the alerts sync pass. Returns True on success.

    Load contact-point + policy + rules from ``args.alerts_dir``. In
    dry-run, print a structural summary plus the placeholder→UID remap
    (skipping strict resolution so PR-side CI without
    ``GC_CLOUDWATCH_UID`` still passes). In live mode, resolve
    recipients (CLI > env > exit 2), substitute them into the contact-
    point template, then PUT/POST the contact point, root policy, and
    every rule in turn. Per-resource FAIL lines are emitted by the
    post_* helpers; this function aggregates them into the pass summary.
    """
    resources, malformed = load_alert_resources(args.alerts_dir)
    if resources.is_empty and not malformed:
        sys.stderr.write(f"No alert resources found under {args.alerts_dir}\n")
        return False

    # Cross-check receiver names before doing any work: a rule or policy
    # pointing at a receiver the contact point does not define provisions
    # 2xx but never delivers. Fail both the dry-run gate and live publish.
    binding_errors = find_receiver_binding_errors(resources)
    if binding_errors:
        for err in binding_errors:
            sys.stderr.write(f"FAIL: {err}\n")
        return False

    walkable: list[dict[str, Any]] = list(resources.rules)
    if resources.contact_point is not None:
        walkable.append(resources.contact_point)
    if resources.notification_policy is not None:
        walkable.append(resources.notification_policy)

    if args.dry_run:
        remap = build_uid_remap(walkable, strict=False)
        if resources.contact_point is not None:
            print(
                f"DRY RUN: would upsert contact point uid="
                f"{resources.contact_point.get('uid', '<unknown>')}"
            )
        if resources.notification_policy is not None:
            print("DRY RUN: would replace root notification policy")
        if resources.rules:
            print(f"DRY RUN: would upsert {len(resources.rules)} alert rule(s):")
            for rule in resources.rules:
                print(
                    f"  - uid={rule.get('uid', '<unknown>')}  "
                    f"title={rule.get('title', '<no-title>')}"
                )
        if remap:
            print("\nDatasource UID remap (alerts):")
            for placeholder, real in sorted(remap.items()):
                print(f"  {placeholder} -> {real}")
        if malformed:
            sys.stderr.write(
                f"\n{len(malformed)} alert file(s) malformed: "
                f"{', '.join(malformed)}\n"
            )
            return False
        return True

    # Live mode: require the loaded resources. A missing required file
    # surfaces as a malformed entry that we've already printed above;
    # surface a summary failure instead of trying to publish None.
    if not resources.required_present:
        sys.stderr.write(
            "\nAlert sync aborted: contact-points.json and notification-"
            "policy.json are both required (see malformed entries above).\n"
        )
        return False
    # required_present guarantees both are non-None; narrow for the type
    # checker so the publish plan below can pass them as required dicts.
    assert resources.contact_point is not None
    assert resources.notification_policy is not None

    recipients = resolve_recipients(
        args.recipients, dict(os.environ), dry_run=False
    )
    contact_point = apply_recipients_to_contact_point(
        resources.contact_point, recipients
    )

    # Build the UID remap BEFORE publishing so a missing GC_CLOUDWATCH_UID
    # aborts with a clear error instead of silently shipping rules whose
    # CloudWatch queries resolve to nothing.
    remap = build_uid_remap(walkable)
    if remap:
        print("Datasource UID remap (alerts):")
        for placeholder, real in sorted(remap.items()):
            print(f"  {placeholder} -> {real}")
        print()

    cp_uid = str(contact_point.get("uid", "<unknown>"))

    # Ordered publish plan: contact point first (the policy and rules
    # reference its receiver), then the singleton root policy, then each
    # rule. Each entry is (operator-facing id, OK-line label, thunk) — a
    # uniform shape so the publish loop below can apply one fail-fast rule
    # across all three resource kinds.
    publish_plan: list[tuple[str, str, Callable[[], int]]] = [
        (
            cp_uid,
            f"contact-point uid={cp_uid}",
            partial(post_contact_point, args.stack_url, api_key, contact_point),
        ),
        (
            "policy",
            "policy",
            partial(
                post_notification_policy,
                args.stack_url,
                api_key,
                resources.notification_policy,
            ),
        ),
    ]
    for rule in resources.rules:
        uid = str(rule.get("uid", "<unknown>"))
        remapped = remap_datasource_uids(rule, remap)
        publish_plan.append(
            (
                uid,
                f"alert-rule uid={uid}",
                partial(post_alert_rule, args.stack_url, api_key, remapped),
            )
        )

    # Same consecutive-transport-failure fail-fast as the dashboards pass:
    # a contact point + policy + 14 rules is 16 requests, so an
    # unreachable GC would otherwise wait out 16 × HTTP_TIMEOUT_SECONDS
    # (~8 min) before the summary. 599 is post_*'s transport-failure
    # sentinel (URLError); a real HTTP status means GC is reachable and
    # must not trip the counter.
    failed_ids: list[str] = []
    skipped_after_abort: list[str] = []
    consecutive_transport_fails = 0
    aborted = False
    for resource_id, label, publish in publish_plan:
        if aborted:
            skipped_after_abort.append(resource_id)
            continue
        status = publish()
        if 200 <= status < 300:
            print(f"OK  {label} status={status}")
            consecutive_transport_fails = 0
        else:
            failed_ids.append(resource_id)
            if status == 599:
                consecutive_transport_fails += 1
                if consecutive_transport_fails >= _CONSECUTIVE_TRANSPORT_FAIL_LIMIT:
                    sys.stderr.write(
                        f"\nABORT: {consecutive_transport_fails} consecutive transport "
                        f"failures against {args.stack_url}; assuming GC is unreachable "
                        "and skipping the remaining alert resources.\n"
                    )
                    aborted = True
            else:
                consecutive_transport_fails = 0

    total = (
        (1 if resources.contact_point is not None else 0)
        + (1 if resources.notification_policy is not None else 0)
        + len(resources.rules)
        + len(malformed)
    )
    if failed_ids or skipped_after_abort or malformed:
        all_failures = failed_ids + skipped_after_abort + malformed
        parts: list[str] = []
        if skipped_after_abort:
            parts.append(f"{len(skipped_after_abort)} skipped after abort")
        if malformed:
            parts.append(f"{len(malformed)} malformed")
        suffix = f" ({', '.join(parts)})" if parts else ""
        sys.stderr.write(
            f"\n{len(all_failures)} of {total} alert resource(s) failed to "
            f"publish{suffix}: {', '.join(all_failures)}\n"
        )
        return False
    print(f"\nAll {total} alert resource(s) published successfully.")
    return True


if __name__ == "__main__":
    raise SystemExit(main())
