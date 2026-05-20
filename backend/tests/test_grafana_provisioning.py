"""Phase 6 — Grafana CloudWatch datasource provisioning.

Structural invariants. We don't boot Grafana in CI; instead we parse the
provisioning YAML and the compose overlay and assert the secret-wiring Phase 6
relies on. If a future edit drops the `$__file{...}` substitution, stops
mounting the docker secrets, or stops sourcing them from the CLOUDWATCH_* env
vars, this test fails before the demo does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASOURCE_PATH = (
    REPO_ROOT
    / "config"
    / "grafana"
    / "provisioning"
    / "datasources"
    / "cloudwatch.yml"
)
COMPOSE_OVERLAY_PATH = REPO_ROOT / "docker-compose.observability.yml"

ACCESS_SECRET_NAME = "cloudwatch_access_key"
SECRET_SECRET_NAME = "cloudwatch_secret_key"
ACCESS_ENV_VAR = "CLOUDWATCH_ACCESS_KEY"
SECRET_ENV_VAR = "CLOUDWATCH_SECRET_KEY"


def _load_yaml(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8")))


def test_cloudwatch_datasource_file_exists() -> None:
    assert DATASOURCE_PATH.is_file(), (
        f"Missing CloudWatch datasource provisioning file: {DATASOURCE_PATH}"
    )


def test_cloudwatch_datasource_declares_expected_fields() -> None:
    data = _load_yaml(DATASOURCE_PATH)

    # Grafana provisioning v1 contract — the schema Grafana 11.x reads.
    assert data["apiVersion"] == 1

    datasources = data["datasources"]
    assert len(datasources) == 1, "Expected exactly one datasource entry"
    ds = datasources[0]

    # AWS CloudWatch is the datasource type ID; UID is stable so Phase 5
    # dashboards can reference it without per-instance lookup.
    assert ds["type"] == "cloudwatch"
    assert ds["uid"] == "cloudwatch"
    # Server-side proxy keeps creds out of the browser; UI-locked so an
    # operator can't accidentally save over the provisioned config.
    assert ds["access"] == "proxy"
    assert ds["editable"] is False

    json_data = ds["jsonData"]
    # IAM user keys path, not OIDC. Locked decision #7 in the plan.
    assert json_data["authType"] == "keys"
    # Region locked to ap-east-2 (where AMS runs).
    assert json_data["defaultRegion"] == "ap-east-2"

    secure = ds["secureJsonData"]
    # Credentials are read from tmpfs files mounted by docker secrets, NOT
    # from env vars — that's the channel that keeps them out of
    # `docker inspect`'s Env block.
    assert secure["accessKey"] == f"$__file{{/run/secrets/{ACCESS_SECRET_NAME}}}"
    assert secure["secretKey"] == f"$__file{{/run/secrets/{SECRET_SECRET_NAME}}}"


def test_compose_overlay_wires_cloudwatch_secrets_to_grafana() -> None:
    data = _load_yaml(COMPOSE_OVERLAY_PATH)

    # Grafana service must reference both secrets so they get mounted at
    # /run/secrets/ inside the container.
    grafana = data["services"]["grafana"]
    grafana_secrets = grafana.get("secrets", [])
    secret_names = {s if isinstance(s, str) else s["source"] for s in grafana_secrets}
    assert ACCESS_SECRET_NAME in secret_names, (
        f"grafana service must mount the {ACCESS_SECRET_NAME} secret"
    )
    assert SECRET_SECRET_NAME in secret_names, (
        f"grafana service must mount the {SECRET_SECRET_NAME} secret"
    )

    # Grafana must NOT receive the keys as plain env vars — that's the leak
    # channel Phase 6 explicitly closed.
    grafana_env = grafana.get("environment", {}) or {}
    env_keys = (
        set(grafana_env.keys())
        if isinstance(grafana_env, dict)
        else {entry.split("=", 1)[0] for entry in grafana_env}
    )
    assert ACCESS_ENV_VAR not in env_keys, (
        "CLOUDWATCH_ACCESS_KEY must not appear in grafana.environment "
        "(use docker secrets so it stays out of `docker inspect`)"
    )
    assert SECRET_ENV_VAR not in env_keys, (
        "CLOUDWATCH_SECRET_KEY must not appear in grafana.environment "
        "(use docker secrets so it stays out of `docker inspect`)"
    )

    # Top-level `secrets:` block must source values from the host CLOUDWATCH_*
    # env vars; this is how `.env` flows into the secret files.
    top_secrets = data.get("secrets", {})
    assert top_secrets.get(ACCESS_SECRET_NAME, {}).get("environment") == ACCESS_ENV_VAR
    assert top_secrets.get(SECRET_SECRET_NAME, {}).get("environment") == SECRET_ENV_VAR
