#!/usr/bin/env python3
"""Phase 7 regression test: k6 load + stress scripts and compose wiring.

Acts as the TDD gate for Phase 7 (docs/plans/observability-implementation-plan.md).
Runs offline — no k6 binary or images need to be pulled. Fails loudly if a
required script is missing, the compose overlay doesn't declare `k6` /
`traffic-generator` services under the expected profiles, the Makefile lacks
the convenience targets, or a script omits a structural element (BASE_URL
override, scenarios/stages, thresholds).

Run: ``python3 scripts/test_obs_k6.py`` from repo root.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOAD_DIR = REPO_ROOT / "load"
LIB_DIR = LOAD_DIR / "lib"
COMPOSE_OBSERVABILITY = REPO_ROOT / "docker-compose.observability.yml"
COMPOSE_BASE = REPO_ROOT / "docker-compose.yml"
MAKEFILE = REPO_ROOT / "Makefile"
README_LOAD = LOAD_DIR / "README.md"

# Phase 7 ships two AMS-specific scenario shapes (k6-load.js, k6-stress.js) plus
# the four mirrored from the reference lab (smoke, steady, spike, consistent).
# Each lives in load/ at the root so the compose k6 service mounts a single dir.
REQUIRED_SCRIPTS = {
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
        # AMS critical flows (Phase 7 plan):
        "loginFlow",
        "searchAssetsFlow",
        "submitRepairFlow",
        "approveRepairFlow",
        "completeRepairFlow",
        "registerAssetFlow",
    ],
    "fixtures.js": ["JPEG"],
}

REQUIRED_MAKE_TARGETS = [
    "load-smoke",
    "load-steady",
    "load-spike",
    "load-load",
    "load-stress",
    "load-consistent",
    "traffic-start",
    "traffic-stop",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def passed(msg: str) -> None:
    print(f"PASS: {msg}")


def check_scripts() -> None:
    if not LOAD_DIR.is_dir():
        fail(f"{LOAD_DIR} directory missing (Phase 7 scripts not created)")
    for name, spec in REQUIRED_SCRIPTS.items():
        path = LOAD_DIR / name
        if not path.is_file():
            fail(f"required k6 script missing: load/{name}")
        text = path.read_text(encoding="utf-8")
        for needle in spec["must_contain"]:
            if needle not in text:
                fail(f"load/{name} missing required marker {needle!r}")
        # Every script must read BASE_URL from __ENV so the compose k6 service
        # can point it at the backend without rebuilding the image.
        if "__ENV.BASE_URL" not in text:
            fail(f"load/{name} does not honour __ENV.BASE_URL override")
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


def check_compose() -> None:
    if not COMPOSE_OBSERVABILITY.is_file():
        fail(f"{COMPOSE_OBSERVABILITY} missing")
    text = COMPOSE_OBSERVABILITY.read_text(encoding="utf-8")

    # The k6 one-shot runner is profile-gated under `tools` so it doesn't run
    # by default with `make obs-up`.
    if not re.search(r"^\s{2}k6:", text, re.MULTILINE):
        fail("docker-compose.observability.yml missing `k6:` service")
    if "tools" not in text:
        fail("k6 service must declare profile `tools`")

    # The long-running consistent-traffic generator is profile-gated under
    # `traffic` so it can be started/stopped independently.
    if not re.search(r"^\s{2}traffic-generator:", text, re.MULTILINE):
        fail(
            "docker-compose.observability.yml missing `traffic-generator:` "
            "service"
        )
    if "k6-consistent.js" not in text:
        fail("traffic-generator must run /scripts/k6-consistent.js")
    passed("compose overlay declares k6 + traffic-generator services")

    # Parse-time validation via `docker compose config` so we know the merged
    # overlay is well-formed. backend/.env may be git-ignored on fresh clones;
    # stub it like scripts/test_obs_compose.sh does.
    backend_env = REPO_ROOT / "backend" / ".env"
    created_stub = False
    if not backend_env.exists():
        backend_env.write_text("", encoding="utf-8")
        created_stub = True
    try:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(COMPOSE_BASE),
                "-f",
                str(COMPOSE_OBSERVABILITY),
                "--profile",
                "tools",
                "--profile",
                "traffic",
                "config",
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            check=False,
        )
    finally:
        if created_stub:
            backend_env.unlink(missing_ok=True)

    if result.returncode != 0:
        # If docker is unavailable on the runner, skip the parse check rather
        # than fail — the file-shape checks above still gate authoring.
        stderr = result.stderr.strip().lower()
        if "command not found" in stderr or "cannot connect to the docker daemon" in stderr:
            passed("compose parse skipped (docker daemon unavailable)")
            return
        fail(f"docker compose config rejected the overlay:\n{result.stderr}")
    rendered = result.stdout
    for svc in ("k6", "traffic-generator"):
        if not re.search(rf"^\s{{2}}{svc}:", rendered, re.MULTILINE):
            fail(f"rendered config missing service `{svc}` under profiles")
    passed("docker compose config merges k6 + traffic-generator cleanly")


def check_makefile() -> None:
    if not MAKEFILE.is_file():
        fail(f"{MAKEFILE} missing")
    text = MAKEFILE.read_text(encoding="utf-8")
    for target in REQUIRED_MAKE_TARGETS:
        # Match a recipe line like `load-smoke:` (possibly with deps after the
        # colon). Use word boundary on left to avoid `load-smoke` matching
        # `xload-smoke`.
        if not re.search(rf"(^|\s){re.escape(target)}:", text, re.MULTILINE):
            fail(f"Makefile missing target `{target}`")
    passed(f"Makefile declares {len(REQUIRED_MAKE_TARGETS)} load/traffic targets")


def check_readme() -> None:
    if not README_LOAD.is_file():
        fail("load/README.md missing")
    text = README_LOAD.read_text(encoding="utf-8")
    for needle in (
        "make load-smoke",
        "k6-load.js",
        "k6-stress.js",
        # Stress runs must disable the slowapi limiter, per Phase 7 known
        # gotcha. README must document the toggle so the operator doesn't
        # measure the limiter by mistake.
        "RATE_LIMIT_ENABLED",
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
        result = subprocess.run(
            [k6, "inspect", "--quiet", str(LOAD_DIR / name)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            fail(f"k6 inspect rejected load/{name}:\n{result.stderr}")
    passed("k6 inspect parses all scripts")


def main() -> None:
    check_scripts()
    check_lib()
    check_compose()
    check_makefile()
    check_readme()
    maybe_check_k6_inspect()
    print()
    print("OK: Phase 7 k6 invariants hold.")


if __name__ == "__main__":
    main()
