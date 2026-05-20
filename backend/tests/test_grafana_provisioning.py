"""Phase 6 — Grafana CloudWatch datasource provisioning.

Structural invariants. We don't boot Grafana in CI; instead we assert that the
provisioning YAML and the compose overlay carry the env-var hooks Phase 6
relies on. If a future edit drops the ${CLOUDWATCH_*} substitution or stops
passing the keys through to the container, this test fails before the demo
does.
"""

from __future__ import annotations

from pathlib import Path

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


def test_cloudwatch_datasource_file_exists() -> None:
    assert DATASOURCE_PATH.is_file(), (
        f"Missing CloudWatch datasource provisioning file: {DATASOURCE_PATH}"
    )


def test_cloudwatch_datasource_declares_expected_fields() -> None:
    text = DATASOURCE_PATH.read_text(encoding="utf-8")
    # Grafana provisioning v1 contract — the schema Grafana 11.x reads.
    assert "apiVersion: 1" in text
    # AWS CloudWatch is the datasource type ID.
    assert "type: cloudwatch" in text
    # IAM user keys path, not OIDC. Locked decision #7 in the plan.
    assert "authType: keys" in text
    # Region locked to ap-east-2 (where AMS runs).
    assert "ap-east-2" in text
    # Keys are injected at Grafana startup via env-var substitution so the
    # provisioning file itself stays git-safe.
    assert "${CLOUDWATCH_ACCESS_KEY}" in text
    assert "${CLOUDWATCH_SECRET_KEY}" in text


def test_compose_overlay_passes_cloudwatch_env_to_grafana() -> None:
    text = COMPOSE_OVERLAY_PATH.read_text(encoding="utf-8")
    # Grafana must see these names with `GF_`-style env substitution disabled —
    # the datasource YAML uses ${VAR}, not $__env{VAR}, so the variable has to
    # be present in the container environment when provisioning runs.
    assert "CLOUDWATCH_ACCESS_KEY" in text
    assert "CLOUDWATCH_SECRET_KEY" in text
