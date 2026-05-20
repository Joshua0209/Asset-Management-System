#!/usr/bin/env python3
"""Phase 5 regression test: Grafana provisioning + dashboards are coherent.

Acts as the TDD gate for Phase 5 (docs/plans/observability-implementation-plan.md).
Runs offline — no Grafana container required. Fails loudly if a dashboard JSON
is malformed, declares a duplicate UID, references a datasource UID that
provisioning never declares, or carries a Grafana export artifact that breaks
file-based provisioning (`__inputs` / `__elements`).

Why these checks and not "spin Grafana up and read /api/dashboards":

* Each dashboard's JSON contract with Grafana is its `panels[*].datasource.uid`
  pointing at one of the datasources provisioned by datasources.yml. Catching
  a typo in those UIDs before Grafana boots saves the demo-day debug loop of
  "panels say No data, why?" — Grafana silently degrades to the default DS.
* Removing `__inputs` / `__elements` is a one-time cleanup the plan calls out
  explicitly; missing the cleanup means dashboards load with placeholder
  variables that need manual UI fixup.
* JSON parse failure is the most common authoring mistake (trailing commas,
  unbalanced braces). Catching it offline keeps the obs-up loop fast.

Run: `python3 scripts/test_obs_dashboards.py` from repo root.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARDS_DIR = REPO_ROOT / "config" / "grafana" / "dashboards"
PROVISIONING_DIR = REPO_ROOT / "config" / "grafana" / "provisioning"
DATASOURCES_FILE = PROVISIONING_DIR / "datasources" / "datasources.yml"
DASHBOARDS_PROVISIONING = PROVISIONING_DIR / "dashboards" / "dashboards.yml"

EXPECTED_DASHBOARDS = [
    "00-start-here.json",
    "01-operations-overview.json",
    "02-service-drilldown.json",
    "03-repair-journey.json",
    "04-logs-traces-profiles.json",
    "05-mysql.json",
]

# Datasource type literals that are pseudo / expression sources Grafana hands
# panels without needing a provisioned datasource (markdown text panels, the
# expression engine itself).
PSEUDO_DATASOURCE_UIDS = {"__expr__", "grafana", "-- Grafana --"}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def passing(msg: str) -> None:
    print(f"PASS: {msg}")


def collect_datasource_uids_from_yaml(text: str) -> set[str]:
    """Pull `uid: <value>` declarations out of datasources.yml.

    Uses a regex on `^\\s*uid:\\s*<value>` instead of a full YAML parser so
    the validator stays stdlib-only (CI / local without PyYAML can still run
    it). The schema for datasources.yml is shallow enough that this is fine
    — Grafana itself reads it as a flat key list per entry.
    """
    uids: set[str] = set()
    for line in text.splitlines():
        m = re.match(r"^\s*uid:\s*([A-Za-z0-9_\-]+)\s*$", line)
        if m:
            uids.add(m.group(1))
    return uids


def collect_panel_datasource_uids(panels: list[dict], acc: set[str]) -> None:
    """Recursively collect `datasource.uid` from panels (handles row collapse).

    Grafana row panels nest their children in `.panels[*]`, so a naive
    top-level walk misses panels inside collapsed rows. The recursion mirrors
    what Grafana's own provisioning loader does.
    """
    for panel in panels:
        ds = panel.get("datasource")
        if isinstance(ds, dict):
            uid = ds.get("uid")
            if isinstance(uid, str):
                acc.add(uid)
        elif isinstance(ds, str) and ds:
            acc.add(ds)
        for target in panel.get("targets", []) or []:
            tds = target.get("datasource") if isinstance(target, dict) else None
            if isinstance(tds, dict):
                uid = tds.get("uid")
                if isinstance(uid, str):
                    acc.add(uid)
        # Row panels nest children.
        if panel.get("type") == "row" and isinstance(panel.get("panels"), list):
            collect_panel_datasource_uids(panel["panels"], acc)


def check_dashboard(path: Path, provisioned_uids: set[str], all_uids: dict[str, Path]) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"{path.name} is not valid JSON: {e}")

    # Required top-level fields for file-based provisioning.
    for required in ("uid", "title", "panels", "schemaVersion"):
        if required not in data:
            fail(f"{path.name} missing required top-level field '{required}'")

    if not isinstance(data["panels"], list) or not data["panels"]:
        fail(f"{path.name} has no panels")

    # Cross-dashboard UID uniqueness: Grafana provisioning silently drops the
    # later loader on UID collision, which would make one dashboard invisible
    # without erroring at startup.
    uid = data["uid"]
    if uid in all_uids:
        fail(f"{path.name} UID '{uid}' collides with {all_uids[uid].name}")
    all_uids[uid] = path

    # Export-artifact cleanup. Grafana's UI export injects these blocks; they
    # break file-based provisioning by demanding the input variables be
    # interactively resolved at load time, which provisioning can't do.
    for forbidden in ("__inputs", "__elements", "__requires"):
        if forbidden in data:
            fail(f"{path.name} contains '{forbidden}' export artifact — strip via jq before committing")

    # Datasource cross-ref.
    referenced: set[str] = set()
    collect_panel_datasource_uids(data["panels"], referenced)
    for ref in referenced:
        if ref in PSEUDO_DATASOURCE_UIDS:
            continue
        if ref not in provisioned_uids:
            fail(
                f"{path.name} references datasource uid '{ref}' but provisioning "
                f"declares only {sorted(provisioned_uids)}"
            )

    passing(f"{path.name} OK ({len(data['panels'])} panels, uid={uid})")


def check_dashboards_provisioning() -> None:
    if not DASHBOARDS_PROVISIONING.is_file():
        fail(f"{DASHBOARDS_PROVISIONING.relative_to(REPO_ROOT)} not found")
    text = DASHBOARDS_PROVISIONING.read_text(encoding="utf-8")
    # The provider must point at the path Grafana mounts the dashboards on
    # — anything else makes file-based loading silently no-op.
    if "/var/lib/grafana/dashboards" not in text:
        fail(
            f"{DASHBOARDS_PROVISIONING.name} doesn't reference the mounted "
            "dashboard path /var/lib/grafana/dashboards"
        )
    passing(f"{DASHBOARDS_PROVISIONING.name} OK")


def main() -> int:
    if not DASHBOARDS_DIR.is_dir():
        fail(f"{DASHBOARDS_DIR.relative_to(REPO_ROOT)} is missing")
    if not DATASOURCES_FILE.is_file():
        fail(f"{DATASOURCES_FILE.relative_to(REPO_ROOT)} is missing")

    provisioned_uids = collect_datasource_uids_from_yaml(
        DATASOURCES_FILE.read_text(encoding="utf-8")
    )
    if not provisioned_uids:
        fail(f"{DATASOURCES_FILE.name} declares no datasources (no `uid:` lines found)")
    passing(f"{DATASOURCES_FILE.name} declares uids: {sorted(provisioned_uids)}")

    check_dashboards_provisioning()

    # Each expected dashboard must exist.
    missing = [
        name
        for name in EXPECTED_DASHBOARDS
        if not (DASHBOARDS_DIR / name).is_file()
    ]
    if missing:
        fail(
            "missing dashboards: "
            + ", ".join(missing)
            + f" (looked under {DASHBOARDS_DIR.relative_to(REPO_ROOT)})"
        )

    all_uids: dict[str, Path] = {}
    for name in EXPECTED_DASHBOARDS:
        check_dashboard(DASHBOARDS_DIR / name, provisioned_uids, all_uids)

    print()
    print(f"All {len(EXPECTED_DASHBOARDS)} dashboards + provisioning OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
