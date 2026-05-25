#!/usr/bin/env python3
"""Regression test: k6 load + stress scripts + shared lib helpers.

Acts as the offline structural gate for the k6 surface. Runs without
pulling a k6 binary or image — fails loudly if a required script is
missing, a script omits a structural element (BASE_URL override,
scenarios/stages, thresholds), or `load/README.md` drops the GC
remote-write or RATE_LIMIT_ENABLED guidance.

Phase 5 of `docs/plans/observability-prod-migration-plan.md` deleted the
W6 Phase 7 docker-compose overlay and the Makefile load targets that the
original Phase 7 regression gate also asserted on; those checks are gone
here. The compose-overlay parse-time validation is gone too. What's left
is the script-shape and runbook-shape gate — the only thing the rebased
PR #84 surface can still own offline.

Run: ``python3 scripts/test_obs_k6.py`` from repo root.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn, TypedDict

REPO_ROOT = Path(__file__).resolve().parent.parent
LOAD_DIR = REPO_ROOT / "load"
LIB_DIR = LOAD_DIR / "lib"
README_LOAD = LOAD_DIR / "README.md"


class ScriptSpec(TypedDict):
    """Structural-marker spec for a k6 script.

    ``must_contain`` is a list of substrings the script source MUST contain
    for the regression gate to pass — they pin the script's intent (scenario
    shape, threshold metrics, env-driven duration) so a future edit can't
    silently strip them.
    """

    must_contain: list[str]


# Two AMS-specific scenario shapes (k6-load.js, k6-stress.js) plus the four
# mirrored from the reference lab (smoke, steady, spike, consistent). Each
# lives in load/ at the root so a developer running k6 on the host points at
# a single dir.
REQUIRED_SCRIPTS: dict[str, ScriptSpec] = {
    "k6-load.js": {
        # constant-arrival-rate scenarios + per-flow weighting
        "must_contain": [
            "scenarios",
            "constant-arrival-rate",
            "http_req_duration",
            "http_req_failed",
        ],
    },
    "k6-stress.js": {
        # ramping arrival rate or ramping VUs that walks past breakpoint
        "must_contain": [
            "stages",
            "http_req_duration",
        ],
    },
    "k6-smoke.js": {
        "must_contain": ["vus", "duration"],
    },
    "k6-steady.js": {
        "must_contain": ["stages"],
    },
    "k6-spike.js": {
        "must_contain": ["stages"],
    },
    "k6-consistent.js": {
        # Constant-arrival-rate per flow, configurable via env. Mirrors the
        # reference lab's traffic-generator entrypoint.
        "must_contain": [
            "constant-arrival-rate",
            "TRAFFIC_DURATION",
        ],
    },
}

REQUIRED_LIB = {
    "auth.js": ["login", "BASE_URL"],
    "flows.js": [
        # AMS critical flows:
        "loginFlow",
        "searchAssetsFlow",
        "submitRepairFlow",
        "approveRepairFlow",
        "completeRepairFlow",
        "registerAssetFlow",
    ],
    "fixtures.js": ["JPEG"],
}


def fail(msg: str) -> NoReturn:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def passed(msg: str) -> None:
    print(f"PASS: {msg}")


def check_scripts() -> None:
    if not LOAD_DIR.is_dir():
        fail(f"{LOAD_DIR} directory missing (k6 scripts not created)")
    for name, spec in REQUIRED_SCRIPTS.items():
        path = LOAD_DIR / name
        if not path.is_file():
            fail(f"required k6 script missing: load/{name}")
        text = path.read_text(encoding="utf-8")
        for needle in spec["must_contain"]:
            if needle not in text:
                fail(f"load/{name} missing required marker {needle!r}")
        # Every script must surface BASE_URL from env so the operator can
        # point it at any backend without editing the script. Scripts either
        # read __ENV.BASE_URL directly or import the resolved value from
        # lib/auth.js (which is the convention for the AMS flow scripts).
        reads_env = "__ENV.BASE_URL" in text
        imports_lib = (
            'from "./lib/auth.js"' in text or "from './lib/auth.js'" in text
        )
        uses_base_url = "BASE_URL" in text
        if not (reads_env or (imports_lib and uses_base_url)):
            fail(
                f"load/{name} does not honour BASE_URL "
                "(neither __ENV.BASE_URL nor lib/auth.js import found)",
            )
    passed(f"{len(REQUIRED_SCRIPTS)} k6 scripts present with required markers")


def check_lib() -> None:
    if not LIB_DIR.is_dir():
        fail(f"{LIB_DIR} directory missing (shared k6 helpers not created)")
    for name, needles in REQUIRED_LIB.items():
        path = LIB_DIR / name
        if not path.is_file():
            fail(f"required helper missing: load/lib/{name}")
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                fail(f"load/lib/{name} missing {needle!r}")
    passed(f"{len(REQUIRED_LIB)} k6 lib helpers present")


def check_readme() -> None:
    if not README_LOAD.is_file():
        fail("load/README.md missing")
    text = README_LOAD.read_text(encoding="utf-8")
    for needle in (
        # Direct k6 invocation now that the Makefile / compose-overlay
        # targets are gone (Phase 2 of the prod migration plan).
        "k6 run load/k6-smoke.js",
        "k6-load.js",
        "k6-stress.js",
        # Stress runs must disable the slowapi limiter; the README must
        # document the toggle so the operator doesn't measure the
        # limiter by mistake.
        "RATE_LIMIT_ENABLED",
        # Grafana Cloud remote-write env vars; without these the k6 run
        # metrics never reach the GC dashboards.
        "K6_PROMETHEUS_RW_SERVER_URL",
        "K6_PROMETHEUS_RW_USERNAME",
        "K6_PROMETHEUS_RW_PASSWORD",
    ):
        if needle not in text:
            fail(f"load/README.md missing required guidance {needle!r}")
    passed("load/README.md documents the runbook")


def maybe_check_k6_inspect() -> None:
    # When the k6 binary is available locally we let it parse the scripts as a
    # cheap belt-and-suspenders check. CI runs the same gate inside the docker
    # image (`grafana/k6:0.54.0 inspect`), but doing it here when available
    # catches syntax mistakes before commit.
    k6 = shutil.which("k6")
    if k6 is None:
        passed("k6 inspect skipped (k6 binary not on PATH)")
        return
    for name in REQUIRED_SCRIPTS:
        try:
            result = subprocess.run(
                [k6, "inspect", "--quiet", str(LOAD_DIR / name)],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            # A wedged or slow k6 binary turns a structural gate into a
            # stuck CI job; bail fast with a clear message instead of
            # blocking the run.
            fail(f"k6 inspect timed out (>30s) on load/{name}")
        if result.returncode != 0:
            # Include stdout: k6 inspect emits the parse diagnostic body
            # on stdout (the structured report) and only the short error
            # summary on stderr. Showing both means the operator sees the
            # full failure context without a manual re-run.
            fail(
                f"k6 inspect rejected load/{name}:\n"
                f"--- stdout ---\n{result.stdout}\n"
                f"--- stderr ---\n{result.stderr}"
            )
    passed("k6 inspect parses all scripts")


def main() -> None:
    check_scripts()
    check_lib()
    check_readme()
    maybe_check_k6_inspect()
    print()
    print("OK: k6 load surface invariants hold.")


if __name__ == "__main__":
    main()
